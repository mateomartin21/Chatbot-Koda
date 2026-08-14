"""Generacion de planes (R1-R8). Patron Strategy: una clase por distancia.

Todo el algoritmo comun vive en EstrategiaPlan; cada distancia solo aporta sus
parametros. Anadir un ultra manana = una clase mas y una entrada en factory.py, sin
tocar nada de esto (Open/Closed) — ver docs/adr/ADR-006-dominio-determinista.md.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.domain.models import Runner
from app.domain.training.modelos import (
    Alternativa,
    Distancia,
    Nivel,
    Objetivo,
    PlanEntrenamiento,
    PlanNoViable,
    SemanaPlan,
    Sesion,
    TipoSesion,
)
from app.domain.training.paces import ZonasRitmo, zonas_para

# --- Reglas transversales -------------------------------------------------------

_SUBIDA_MAXIMA = 1.10  # R1: nunca mas de +10% sobre la semana anterior
_CADA_CUANTAS_SEMANAS_DESCARGA = 4  # R3
_RECORTE_TAPER = 0.70  # R4: cada semana de taper baja un 30%
_TOPE_TIRADA_LARGA = 0.35  # R8: ninguna sesion pasa del 35% del volumen semanal
_FRACCION_TIRADA_LARGA = 0.32
_FRACCION_INTENSIDAD = 0.20  # R2: 80/20 polarizado

# R3 dice "recortar ~30%" y R1 "no subir mas de 10%". Aplicadas al pie de la letra
# semana a semana son incompatibles: tras un recorte del 30%, volver al volumen previo
# exigiria un salto del +43%, y limitar la vuelta al +10% hace que el plan ENCOJA
# (1.10^3 x 0.70 = 0.93 por bloque de cuatro semanas). Se recorta un 20%, que si deja
# progresar (1.10^3 x 0.80 = 1.06 por bloque) sin renunciar a la semana de asimilacion.
# Ver docs/adr/ADR-012-descarga-del-20-por-ciento.md.
_RECORTE_DESCARGA = 0.80

# Dias de la semana en que se corre, segun cuantos dias tenga disponibles el runner
# (0 = lunes). El domingo siempre entra: es el dia de la tirada larga.
_DIAS_POR_FRECUENCIA: dict[int, tuple[int, ...]] = {
    3: (1, 3, 6),
    4: (1, 3, 5, 6),
    5: (1, 2, 3, 5, 6),
    6: (1, 2, 3, 4, 5, 6),
}
_DIA_TIRADA_LARGA = 6

# R7: un principiante nunca corre mas de 4 dias, aunque diga que tiene los 7 libres.
_MAX_DIAS_POR_NIVEL: dict[Nivel, int] = {Nivel.PRINCIPIANTE: 4, Nivel.INTERMEDIO: 5, Nivel.AVANZADO: 6}

_AJUSTE_VOLUMEN_POR_NIVEL: dict[Nivel, float] = {
    Nivel.PRINCIPIANTE: 0.8,
    Nivel.INTERMEDIO: 1.0,
    Nivel.AVANZADO: 1.2,
}


class EstrategiaPlan(ABC):
    """Template method: generar() es igual para todos; lo que cambia son los numeros."""

    @abstractmethod
    def distancia(self) -> Distancia: ...

    @abstractmethod
    def semanas_minimas(self) -> int: ...

    @abstractmethod
    def semanas_maximas(self) -> int: ...

    @abstractmethod
    def volumen_inicial_km(self) -> float: ...

    @abstractmethod
    def volumen_pico_km(self) -> float: ...

    @abstractmethod
    def tirada_larga_maxima_km(self) -> float: ...

    @abstractmethod
    def semanas_taper(self) -> int: ...

    def requisito_previo(self) -> str | None:
        """Lo que hay que traer de casa antes de empezar (§3.1). Solo informativo."""
        return None

    # --- Algoritmo comun --------------------------------------------------------

    def generar(self, runner: Runner, objetivo: Objetivo, hoy: date | None = None) -> PlanEntrenamiento:
        hoy = hoy or date.today()
        nivel = Nivel.desde_texto(runner.nivel)
        disponibles = objetivo.semanas_hasta(hoy)

        self._exigir_semanas_suficientes(disponibles)

        semanas_totales = min(disponibles, self.semanas_maximas())
        zonas = zonas_para(
            distancia=self.distancia(),
            nivel=nivel,
            marca_distancia_km=runner.marca_distancia_km,
            marca_tiempo_seg=runner.marca_tiempo_seg,
        )
        dias = self._dias_de_carrera(runner, nivel)
        volumenes = self._progresion_de_volumen(semanas_totales, nivel, len(dias))

        semanas = tuple(
            self._construir_semana(numero=i + 1, volumen=v, dias=dias, zonas=zonas, total=semanas_totales)
            for i, v in enumerate(volumenes)
        )
        return PlanEntrenamiento(
            distancia=self.distancia(),
            semanas=semanas,
            zonas=zonas,
            ritmos_estimados=zonas.estimados,
            notas=self._notas(zonas, disponibles, semanas_totales),
        )

    def _exigir_semanas_suficientes(self, disponibles: int) -> None:
        """R6: si no da tiempo, el sistema se NIEGA y propone algo concreto."""
        if disponibles >= self.semanas_minimas():
            return
        alternativa = _distancia_inmediatamente_menor(self.distancia())
        raise PlanNoViable(
            f"Preparar un {self.distancia().etiqueta} en {disponibles} semanas no es seguro: "
            f"hacen falta al menos {self.semanas_minimas()}.",
            Alternativa(
                distancia=alternativa,
                motivo=(
                    f"Con {disponibles} semanas por delante, apuntar a un "
                    f"{alternativa.etiqueta} es realista y te deja base construida. "
                    f"El {self.distancia().etiqueta} lo movemos a una fecha mas lejana."
                ),
                semanas_disponibles=disponibles,
            ),
        )

    def _progresion_de_volumen(self, semanas: int, nivel: Nivel, dias_corriendo: int) -> list[float]:
        """R1 + R3 + R4, en este orden de prioridad.

        Cada semana se trunca a decimas ANTES de calcular la siguiente. Si se arrastrara
        el valor exacto y solo se redondeara al final, el redondeo podria empujar una
        semana por encima del +10% real respecto a la anterior ya redondeada: la regla
        se cumpliria sobre el papel y no sobre el plan que recibe el runner.
        """
        ajuste = _AJUSTE_VOLUMEN_POR_NIVEL[nivel]
        fraccion_larga, _ = _reparto_segun_frecuencia(dias_corriendo)
        # El techo real no lo pone la ambicion, lo ponen los dias disponibles: por
        # encima de este volumen la tirada larga topa en su maximo y el sobrante tendria
        # que ir a un rodaje "facil" mas largo que ella. Antes que generar esa semana
        # absurda, el plan deja de crecer.
        pico = min(self.volumen_pico_km() * ajuste, self.tirada_larga_maxima_km() / fraccion_larga)
        primera_de_taper = semanas - self.semanas_taper()

        volumenes = [_a_decimas(min(self.volumen_inicial_km() * ajuste, pico))]
        for numero in range(2, semanas + 1):
            previa = volumenes[-1]
            if numero > primera_de_taper:  # R4
                siguiente = previa * _RECORTE_TAPER
            elif numero % _CADA_CUANTAS_SEMANAS_DESCARGA == 0:  # R3
                siguiente = previa * _RECORTE_DESCARGA
            else:  # R1
                siguiente = min(previa * _SUBIDA_MAXIMA, pico)
            volumenes.append(_a_decimas(siguiente))
        return volumenes

    def _dias_de_carrera(self, runner: Runner, nivel: Nivel) -> tuple[int, ...]:
        """R7: siempre queda al menos un dia de descanso, y el tope del nivel manda
        sobre lo que el runner diga que tiene disponible."""
        # Por debajo de 3 dias no se puede repartir 80/20 sin que la tirada larga se
        # coma la semana entera (violando R8), asi que 3 es el minimo real.
        pedidos = runner.dias_disponibles or 3
        dias = max(3, min(pedidos, _MAX_DIAS_POR_NIVEL[nivel], 6))
        return _DIAS_POR_FRECUENCIA[dias]

    def _construir_semana(
        self, *, numero: int, volumen: float, dias: tuple[int, ...], zonas: ZonasRitmo, total: int
    ) -> SemanaPlan:
        es_taper = numero > total - self.semanas_taper()
        es_descarga = not es_taper and numero % _CADA_CUANTAS_SEMANAS_DESCARGA == 0

        # Todo el reparto se hace en decimas enteras de km para que la suma de las
        # sesiones sea EXACTAMENTE el volumen planificado. Si no, el redondeo de cada
        # sesion se acumula y la semana acaba pesando mas de lo que R1 permite.
        total_d = round(volumen * 10)
        fraccion_larga, _tope = _reparto_segun_frecuencia(len(dias))
        largo_d = min(
            int(total_d * fraccion_larga),
            int(self.tirada_larga_maxima_km() * 10),
        )
        calidad_d = int(total_d * _FRACCION_INTENSIDAD)  # R2

        dias_calidad = self._dias_de_calidad(dias, es_taper)
        dias_faciles = [d for d in dias if d != _DIA_TIRADA_LARGA and d not in dias_calidad]
        faciles_d = total_d - largo_d - calidad_d
        if not dias_faciles:  # sin dias faciles, ese volumen no cabe en ningun sitio
            faciles_d = 0
            largo_d = total_d - calidad_d

        reparto_calidad = dict(zip(dias_calidad, _repartir(calidad_d, len(dias_calidad)), strict=True))
        reparto_facil = dict(zip(dias_faciles, _repartir(faciles_d, len(dias_faciles)), strict=True))

        sesiones: list[Sesion] = []
        for dia in range(7):
            if dia == _DIA_TIRADA_LARGA:
                sesiones.append(self._sesion_larga(dia, largo_d / 10, zonas))
            elif dia in reparto_calidad:
                sesiones.append(
                    self._sesion_de_calidad(dia, reparto_calidad[dia] / 10, zonas, es_taper, dias_calidad)
                )
            elif dia in reparto_facil:
                sesiones.append(self._sesion_facil(dia, reparto_facil[dia] / 10, zonas))
            else:
                sesiones.append(
                    Sesion(dia_semana=dia, tipo=TipoSesion.DESCANSO, distancia_km=0.0, descripcion="Descanso")
                )
        return SemanaPlan(numero=numero, sesiones=tuple(sesiones), es_descarga=es_descarga, es_taper=es_taper)

    def _dias_de_calidad(self, dias: tuple[int, ...], es_taper: bool) -> tuple[int, ...]:
        """En taper se mantiene UNA sesion de intensidad: se baja volumen, no chispa.

        Dos sesiones de calidad solo a partir de 5 dias. Con 4, la segunda dejaria un
        unico dia facil cargando con casi la mitad del volumen semanal — un "rodaje
        suave" mas largo que la tirada larga, que es justo lo que R8 quiere evitar.
        """
        candidatos = [d for d in dias if d != _DIA_TIRADA_LARGA]
        if not candidatos:
            return ()
        cuantas = 1 if (es_taper or len(dias) < 5) else 2
        return tuple(candidatos[:cuantas])

    def _sesion_larga(self, dia: int, km: float, zonas: ZonasRitmo) -> Sesion:
        return Sesion(
            dia_semana=dia,
            tipo=TipoSesion.LARGO,
            distancia_km=round(km, 1),
            descripcion=f"Tirada larga {round(km, 1)} km a {zonas.larga}",
            ritmo_objetivo_seg_km=zonas.larga.seg_por_km,
        )

    def _sesion_facil(self, dia: int, km: float, zonas: ZonasRitmo) -> Sesion:
        return Sesion(
            dia_semana=dia,
            tipo=TipoSesion.FACIL,
            distancia_km=round(km, 1),
            descripcion=f"Rodaje facil {round(km, 1)} km a {zonas.facil}",
            ritmo_objetivo_seg_km=zonas.facil.seg_por_km,
        )

    def _sesion_de_calidad(
        self, dia: int, km: float, zonas: ZonasRitmo, es_taper: bool, dias_calidad: tuple[int, ...]
    ) -> Sesion:
        # Con dos sesiones de calidad, la primera es de series y la segunda de tempo.
        if dia == dias_calidad[0] and not es_taper:
            return Sesion(
                dia_semana=dia,
                tipo=TipoSesion.SERIES,
                distancia_km=round(km, 1),
                descripcion=(
                    f"Series: {round(km, 1)} km de trabajo a {zonas.intervalos}, "
                    "con trote suave entre repeticiones"
                ),
                ritmo_objetivo_seg_km=zonas.intervalos.seg_por_km,
            )
        return Sesion(
            dia_semana=dia,
            tipo=TipoSesion.TEMPO,
            distancia_km=round(km, 1),
            descripcion=f"Tempo: {round(km, 1)} km continuos a {zonas.tempo}",
            ritmo_objetivo_seg_km=zonas.tempo.seg_por_km,
        )

    def _notas(self, zonas: ZonasRitmo, disponibles: int, usadas: int) -> tuple[str, ...]:
        notas: list[str] = []
        if zonas.estimados:
            notas.append(
                "Los ritmos son una estimacion porque todavia no hay una marca reciente. "
                "Los ajustamos despues de tu primera semana."
            )
        if disponibles > usadas:
            notas.append(
                f"Quedan {disponibles} semanas hasta la carrera y el plan ocupa {usadas}: "
                f"empezamos mas adelante o alargamos la base."
            )
        if requisito := self.requisito_previo():
            notas.append(requisito)
        return tuple(notas)


def _reparto_segun_frecuencia(dias_corriendo: int) -> tuple[float, float]:
    """Que fraccion del volumen se lleva la tirada larga, y el techo por sesion (R8).

    R8 fija ese techo en el 35%, pero eso asume semanas de 5-6 dias. Con solo 3, tres
    sesiones de <=35% obligan a que las tres sean casi identicas: eso no es entrenar,
    es repetir. En quien corre 3 dias, la tirada larga ES proporcionalmente mas larga
    — asi funcionan los planes reales. Ver docs/adr/ADR-012-tensiones-entre-reglas.md.
    """
    if dias_corriendo <= 3:
        return 0.42, 0.45
    return _FRACCION_TIRADA_LARGA, _TOPE_TIRADA_LARGA


def _a_decimas(km: float) -> float:
    """Trunca (no redondea) a decimas de kilometro: hacia abajo nunca se incumple un tope."""
    return int(km * 10) / 10


def _repartir(total_decimas: int, partes: int) -> list[int]:
    """Reparte decimas enteras en 'partes' trozos casi iguales que suman EXACTAMENTE
    el total. Sumar trozos redondeados por separado no da el total y desviaba el
    volumen semanal por encima de lo planificado."""
    if partes <= 0:
        return []
    base, resto = divmod(total_decimas, partes)
    return [base + (1 if i < resto else 0) for i in range(partes)]


def _distancia_inmediatamente_menor(distancia: Distancia) -> Distancia:
    orden = [Distancia.K5, Distancia.K10, Distancia.K21, Distancia.K42]
    return orden[max(0, orden.index(distancia) - 1)]


class Plan5K(EstrategiaPlan):
    def distancia(self) -> Distancia:
        return Distancia.K5

    def semanas_minimas(self) -> int:
        return 6

    def semanas_maximas(self) -> int:
        return 10

    def volumen_inicial_km(self) -> float:
        return 15.0

    def volumen_pico_km(self) -> float:
        return 35.0

    def tirada_larga_maxima_km(self) -> float:
        return 10.0

    def semanas_taper(self) -> int:
        return 1


class Plan10K(EstrategiaPlan):
    def distancia(self) -> Distancia:
        return Distancia.K10

    def semanas_minimas(self) -> int:
        return 8

    def semanas_maximas(self) -> int:
        return 12

    def volumen_inicial_km(self) -> float:
        return 25.0

    def volumen_pico_km(self) -> float:
        return 50.0

    def tirada_larga_maxima_km(self) -> float:
        return 14.0

    def semanas_taper(self) -> int:
        return 2

    def requisito_previo(self) -> str | None:
        return "Para este plan conviene poder correr ya 20-30 minutos seguidos."


class Plan21K(EstrategiaPlan):
    def distancia(self) -> Distancia:
        return Distancia.K21

    def semanas_minimas(self) -> int:
        return 12

    def semanas_maximas(self) -> int:
        return 16

    def volumen_inicial_km(self) -> float:
        return 35.0

    def volumen_pico_km(self) -> float:
        return 70.0

    def tirada_larga_maxima_km(self) -> float:
        return 19.0

    def semanas_taper(self) -> int:
        return 2

    def requisito_previo(self) -> str | None:
        return "Para este plan conviene llegar con una base de unos 20 km por semana."


class Plan42K(EstrategiaPlan):
    def distancia(self) -> Distancia:
        return Distancia.K42

    def semanas_minimas(self) -> int:
        return 16

    def semanas_maximas(self) -> int:
        return 20

    def volumen_inicial_km(self) -> float:
        return 50.0

    def volumen_pico_km(self) -> float:
        return 95.0

    def tirada_larga_maxima_km(self) -> float:
        return 32.0

    def semanas_taper(self) -> int:
        return 3

    def requisito_previo(self) -> str | None:
        return "Para este plan conviene haber completado antes un 21K."

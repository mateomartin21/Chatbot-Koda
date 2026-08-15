"""Calculo de ritmos (R5). Funciones puras, sin E/S y sin dependencias externas.

El LLM no calcula nada de esto: solo lo explica en voz alta — ver
docs/adr/ADR-006-dominio-determinista.md.
"""

from dataclasses import dataclass

from app.domain.training.modelos import Distancia, Nivel, ValorInvalido

# Exponente clasico de Peter Riegel (1977). Modela como se degrada el ritmo al subir
# de distancia.
_EXPONENTE_RIEGEL = 1.06

# Riegel SOBREESTIMA el rendimiento en distancias largas para quien tiene poca base:
# asume una resistencia que un principiante todavia no ha construido. Se corrige
# alargando el tiempo previsto segun el nivel. Reconocer donde falla tu propio modelo
# es parte del trabajo — ver docs/contexto/02-DOMINIO-RUNNING.md §2.1.
_CORRECCION_LARGA_DISTANCIA: dict[Nivel, float] = {
    Nivel.PRINCIPIANTE: 1.08,
    Nivel.INTERMEDIO: 1.04,
    Nivel.AVANZADO: 1.00,
}

# Desplazamientos sobre el ritmo umbral, en segundos por kilometro
# (docs/contexto/02-DOMINIO-RUNNING.md §2.2; se toma el punto medio de cada rango).
_SEGUNDOS_SOBRE_UMBRAL = {"facil": 75, "larga": 60, "tempo": 0, "intervalos": -20}

# Ritmos umbral de partida cuando no hay ninguna marca reciente, en seg/km.
_UMBRAL_ESTIMADO_POR_NIVEL: dict[Nivel, float] = {
    Nivel.PRINCIPIANTE: 6 * 60 + 30,
    Nivel.INTERMEDIO: 5 * 60 + 15,
    Nivel.AVANZADO: 4 * 60 + 15,
}


@dataclass(frozen=True)
class Ritmo:
    """Segundos por kilometro. Value object inmutable: nunca se pasa un ritmo como
    float suelto, que es como se cuelan los bugs de unidades."""

    seg_por_km: float

    def __post_init__(self) -> None:
        if self.seg_por_km <= 0:
            raise ValorInvalido("Un ritmo tiene que ser positivo")

    def __str__(self) -> str:
        minutos, segundos = divmod(round(self.seg_por_km), 60)
        return f"{minutos}:{segundos:02d}/km"

    def mas_lento(self, segundos: float) -> "Ritmo":
        return Ritmo(self.seg_por_km + segundos)


@dataclass(frozen=True)
class ZonasRitmo:
    facil: Ritmo
    larga: Ritmo
    tempo: Ritmo
    intervalos: Ritmo
    objetivo: Ritmo
    # True cuando no habia marca reciente y todo esto sale de una estimacion. El coach
    # tiene que decirlo en voz alta: transparencia sobre la incertidumbre (§2.3).
    estimados: bool = False


# Banda de lo humanamente creible para una marca personal, en segundos por kilometro.
# Por debajo de 2:00/km no hay marca mundial que valga — el record de 1500 m ronda los
# 2:17/km — y por encima de 20:00/km se anda mas rapido que eso. Fuera de esa banda una
# marca no es un dato: es una errata.
_RITMO_MAS_RAPIDO_CREIBLE = 2 * 60
_RITMO_MAS_LENTO_CREIBLE = 20 * 60

# Riegel se ajusto con carreras de fondo; por debajo de 1 km extrapola cualquier cosa.
_DISTANCIA_CREIBLE_KM = (1.0, 100.0)


def marca_creible(distancia_km: float | None, tiempo_seg: float | None) -> bool:
    """Si una marca personal puede ser de una persona corriendo.

    Existe por un caso real: el campo del tiempo se rellenaba desde el movil con un
    teclado numerico sin tecla ":", asi que "30" —por treinta minutos— entraba como
    treinta segundos. Un 5K en 30 s da un umbral de 6 seg/km, y el ritmo de intervalos,
    que son 20 seg/km MAS RAPIDO que el umbral, salia negativo. El plan reventaba con
    "un ritmo tiene que ser positivo", el coach decia "error interno" y el runner se
    quedaba sin plan sin que nada explicara por que.

    Se comprueba aqui y no en el formulario a proposito: la marca tambien entra
    hablando, y una regla que solo vive en un formulario no protege al dominio.
    """
    if not distancia_km or not tiempo_seg:
        return False
    minima, maxima = _DISTANCIA_CREIBLE_KM
    if not minima <= distancia_km <= maxima:
        return False
    return _RITMO_MAS_RAPIDO_CREIBLE <= tiempo_seg / distancia_km <= _RITMO_MAS_LENTO_CREIBLE


def predecir_tiempo(t1_seg: float, d1_km: float, d2_km: float) -> float:
    """Predice el tiempo en d2 a partir de una marca en d1 (Riegel)."""
    if t1_seg <= 0 or d1_km <= 0 or d2_km <= 0:
        raise ValorInvalido("Distancias y tiempos deben ser positivos")
    return t1_seg * (d2_km / d1_km) ** _EXPONENTE_RIEGEL


def predecir_tiempo_carrera(t1_seg: float, d1_km: float, distancia: Distancia, nivel: Nivel) -> float:
    """Como predecir_tiempo, pero aplicando la correccion conservadora de larga
    distancia. Es lo que se usa para prometerle un tiempo a alguien."""
    estimado = predecir_tiempo(t1_seg, d1_km, distancia.km)
    if distancia in (Distancia.K21, Distancia.K42):
        estimado *= _CORRECCION_LARGA_DISTANCIA[nivel]
    return estimado


def ritmo_umbral(t1_seg: float, d1_km: float) -> Ritmo:
    """Ritmo que el runner puede sostener aproximadamente una hora.

    Se invierte Riegel para hallar que distancia recorreria en 3600 s; el ritmo a esa
    distancia ES el umbral, por definicion. Mas honesto que asumir "el ritmo de 10K",
    que solo coincide con la hora para corredores de cierto nivel.
    """
    if t1_seg <= 0 or d1_km <= 0:
        raise ValorInvalido("Distancias y tiempos deben ser positivos")
    km_en_una_hora = d1_km * (3600 / t1_seg) ** (1 / _EXPONENTE_RIEGEL)
    return Ritmo(3600 / km_en_una_hora)


def umbral_estimado(nivel: Nivel, minutos_continuos: int | None = None) -> Ritmo:
    """Cuando no hay marca reciente (§2.3): nivel autodeclarado + cuanto aguanta
    corriendo sin parar. Arranca conservador a proposito."""
    base = _UMBRAL_ESTIMADO_POR_NIVEL[nivel]
    if minutos_continuos is not None and minutos_continuos < 20:
        base += 30  # aguanta poco seguido: se asume todavia menos base
    return Ritmo(base)


def zonas_para(
    *,
    distancia: Distancia,
    nivel: Nivel,
    marca_distancia_km: float | None,
    marca_tiempo_seg: float | None,
    minutos_continuos: int | None = None,
) -> ZonasRitmo:
    """Las cinco zonas de entrenamiento, salgan de una marca real o de una estimacion."""
    # Una marca imposible se ignora en vez de romper el plan. El runner no se queda
    # sin nada: se cae a la estimacion por nivel, que es el mismo camino de quien no
    # ha dado ninguna marca, y `estimados` queda en True para que el coach diga en voz
    # alta que estos ritmos son aproximados (§2.3).
    hay_marca = marca_creible(marca_distancia_km, marca_tiempo_seg)
    if hay_marca:
        umbral = ritmo_umbral(marca_tiempo_seg, marca_distancia_km)
        tiempo_meta = predecir_tiempo_carrera(marca_tiempo_seg, marca_distancia_km, distancia, nivel)
        objetivo = Ritmo(tiempo_meta / distancia.km)
    else:
        umbral = umbral_estimado(nivel, minutos_continuos)
        # Sin marca no se promete un tiempo de carrera: el ritmo objetivo se ancla al
        # umbral con un margen segun lo larga que sea la prueba.
        objetivo = umbral.mas_lento(_margen_objetivo_sobre_umbral(distancia))

    return ZonasRitmo(
        facil=umbral.mas_lento(_SEGUNDOS_SOBRE_UMBRAL["facil"]),
        larga=umbral.mas_lento(_SEGUNDOS_SOBRE_UMBRAL["larga"]),
        tempo=umbral,
        intervalos=umbral.mas_lento(_SEGUNDOS_SOBRE_UMBRAL["intervalos"]),
        objetivo=objetivo,
        estimados=not hay_marca,
    )


def _margen_objetivo_sobre_umbral(distancia: Distancia) -> float:
    """Cuanto mas larga la carrera, mas lejos del umbral se corre."""
    return {Distancia.K5: -10, Distancia.K10: 5, Distancia.K21: 25, Distancia.K42: 55}[distancia]

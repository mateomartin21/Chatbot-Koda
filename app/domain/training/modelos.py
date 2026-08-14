"""Entidades y value objects del dominio de entrenamiento. Cero imports externos."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:  # paces.py importa de aqui: solo para el type hint, sin ciclo en runtime
    from app.domain.training.paces import ZonasRitmo


class ValorInvalido(ValueError):
    """Dato de entrada imposible (una distancia negativa, un tiempo cero...)."""


class Distancia(Enum):
    K5 = 5
    K10 = 10
    K21 = 21.0975
    K42 = 42.195

    @property
    def km(self) -> float:
        return float(self.value)

    @property
    def etiqueta(self) -> str:
        return {Distancia.K5: "5K", Distancia.K10: "10K", Distancia.K21: "21K", Distancia.K42: "42K"}[self]

    @classmethod
    def desde_km(cls, km: float) -> "Distancia":
        """Acepta tanto el valor exacto (42.195) como el redondeo con el que la gente
        habla y que guarda la BD segun §4 del dominio (42). Fuera de esas cuatro, no
        hay plan: es mejor decirlo que inventarse una estrategia intermedia."""
        for distancia in cls:
            if abs(distancia.km - km) < 1.0:
                return distancia
        raise ValorInvalido(f"No hay planes para {km} km: solo 5, 10, 21 y 42")


class Nivel(Enum):
    PRINCIPIANTE = "principiante"
    INTERMEDIO = "intermedio"
    AVANZADO = "avanzado"

    @classmethod
    def desde_texto(cls, texto: str | None) -> "Nivel":
        """El nivel llega de un perfil que el usuario rellena hablando, asi que puede
        venir vacio o escrito de cualquier forma. Ante la duda, el mas conservador."""
        if not texto:
            return cls.PRINCIPIANTE
        try:
            return cls(texto.strip().lower())
        except ValueError:
            return cls.PRINCIPIANTE


class TipoSesion(Enum):
    FACIL = "facil"
    SERIES = "series"
    TEMPO = "tempo"
    LARGO = "largo"
    DESCANSO = "descanso"
    CRUZADO = "cruzado"


@dataclass(frozen=True)
class Sesion:
    dia_semana: int  # 0 = lunes
    tipo: TipoSesion
    distancia_km: float
    descripcion: str
    ritmo_objetivo_seg_km: float | None = None


@dataclass(frozen=True)
class SemanaPlan:
    numero: int  # 1 = primera semana del plan
    sesiones: tuple[Sesion, ...]
    es_descarga: bool = False
    es_taper: bool = False

    @property
    def volumen_km(self) -> float:
        return sum(s.distancia_km for s in self.sesiones)


@dataclass(frozen=True)
class Objetivo:
    distancia: Distancia
    fecha_carrera: date
    nombre_carrera: str | None = None
    tiempo_meta_seg: float | None = None

    def semanas_hasta(self, desde: date) -> int:
        return max(0, (self.fecha_carrera - desde).days // 7)


@dataclass(frozen=True)
class PlanEntrenamiento:
    distancia: Distancia
    semanas: tuple[SemanaPlan, ...]
    zonas: "ZonasRitmo"
    ritmos_estimados: bool = False
    notas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def volumen_total_km(self) -> float:
        return sum(s.volumen_km for s in self.semanas)


@dataclass(frozen=True)
class Alternativa:
    """Lo que Koda propone EN LUGAR del objetivo imposible. Sin esto, un rechazo es
    solo un 'no'."""

    distancia: Distancia
    motivo: str
    semanas_disponibles: int


class PlanNoViable(Exception):
    """R6: no hay semanas suficientes para preparar la distancia con seguridad.

    No es un error tecnico, es una decision de entrenamiento: el caso de uso la
    traduce en una respuesta conversacional con su alternativa.
    """

    def __init__(self, mensaje: str, alternativa: Alternativa) -> None:
        super().__init__(mensaje)
        self.alternativa = alternativa


# --- El plan una vez guardado ---------------------------------------------------
#
# PlanEntrenamiento es el resultado de un calculo: no tiene dueno, ni identidad, ni
# fechas — solo "semana 3, dia 6". Lo de abajo es ese mismo plan ya aterrizado en el
# calendario de una persona concreta. Se separa a proposito: la estrategia sigue
# siendo una funcion pura testeable sin base de datos.


class EstadoObjetivo(Enum):
    ACTIVO = "activo"
    COMPLETADO = "completado"
    ABANDONADO = "abandonado"


def fecha_inicio_para(objetivo: Objetivo, semanas_del_plan: int, hoy: date) -> date:
    """El plan se ancla al FINAL, no al principio: su ultima semana es la de la carrera.

    Anclarlo al inicio dejaria el taper cayendo en cualquier sitio — y un taper que no
    termina el dia de la carrera no es un taper, es una semana suave a destiempo.
    """
    lunes_de_la_carrera = objetivo.fecha_carrera - timedelta(days=objetivo.fecha_carrera.weekday())
    inicio = lunes_de_la_carrera - timedelta(weeks=semanas_del_plan - 1)
    # Si el redondeo a semanas completas deja el arranque en el pasado, se empieza hoy:
    # mas vale una primera semana corta que un plan que nace con sesiones vencidas.
    lunes_de_hoy = hoy - timedelta(days=hoy.weekday())
    return max(inicio, lunes_de_hoy)


@dataclass(frozen=True)
class SesionProgramada:
    """Una sesion con su fecha real. Es lo que se le enseña al runner y lo que se
    guarda en la tabla sesiones."""

    sesion: Sesion
    semana: int
    fecha: date
    completada: bool = False


@dataclass(frozen=True)
class PlanActivo:
    """Un PlanEntrenamiento con identidad, dueno y calendario."""

    id: UUID
    objetivo: Objetivo
    plan: PlanEntrenamiento
    fecha_inicio: date
    generado_en: datetime
    version: int = 1
    # (semana, dia_semana) de las sesiones ya completadas. Se guarda aparte del plan
    # porque el plan es el calculo y esto es historia del runner.
    completadas: frozenset[tuple[int, int]] = field(default_factory=frozenset)

    def sesiones_programadas(self, *, incluir_descansos: bool = False) -> tuple[SesionProgramada, ...]:
        """Las sesiones con fecha. Unico sitio donde "semana 3, dia 6" se vuelve un dia
        del calendario: si esto se calculara tambien en la API o en el repositorio,
        tarde o temprano dos de los tres darian fechas distintas.

        La carrera cierra el plan. Las semanas van de lunes a domingo, asi que la
        ultima suele sobrepasar el dia de la carrera; enseñar "domingo, 6 km suaves"
        dos dias DESPUES del maraton es de las cosas que delatan que nadie miro el
        calendario. La carrera es la ultima sesion.
        """
        programadas: list[SesionProgramada] = []
        for semana in self.plan.semanas:
            for sesion in semana.sesiones:
                if not incluir_descansos and sesion.tipo is TipoSesion.DESCANSO:
                    continue
                fecha = self.fecha_inicio + timedelta(weeks=semana.numero - 1, days=sesion.dia_semana)
                if fecha > self.objetivo.fecha_carrera:
                    continue
                programadas.append(
                    SesionProgramada(
                        sesion=sesion,
                        semana=semana.numero,
                        fecha=fecha,
                        completada=(semana.numero, sesion.dia_semana) in self.completadas,
                    )
                )
        return tuple(programadas)

    def proxima_sesion(self, desde: date) -> SesionProgramada | None:
        """La siguiente sesion pendiente a partir de una fecha. None si el plan ya paso."""
        return next(
            (s for s in self.sesiones_programadas() if s.fecha >= desde and not s.completada),
            None,
        )

"""Entidades y value objects del dominio de entrenamiento. Cero imports externos."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

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

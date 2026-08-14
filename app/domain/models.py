"""Entidades del dominio. Cero imports externos — ver tests/unit/test_arquitectura.py."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Runner:
    """El usuario de la app. Raiz de agregacion y frontera de aislamiento (runner_id)."""

    id: UUID
    email: str
    creado_en: datetime
    activo: bool = True
    ultimo_acceso: datetime | None = None
    nombre: str | None = None
    edad: int | None = None
    nivel: str | None = None
    dias_disponibles: int | None = None
    zona_horaria: str | None = None
    marca_distancia_km: float | None = None
    marca_tiempo_seg: float | None = None


@dataclass(frozen=True)
class DatosPerfil:
    """Los campos del perfil que el runner puede rellenar (por formulario o hablando).

    Todo opcional a proposito: el perfil se completa a trozos, en varias conversaciones.
    Un campo en None significa "no me lo has dicho todavia", nunca "borralo".
    """

    nombre: str | None = None
    edad: int | None = None
    nivel: str | None = None
    dias_disponibles: int | None = None
    zona_horaria: str | None = None
    marca_distancia_km: float | None = None
    marca_tiempo_seg: float | None = None


@dataclass(frozen=True)
class Mensaje:
    """Un turno de conversacion. Capa 2 de la memoria (docs/contexto/05-MEMORIA.md §2)."""

    rol: str  # "usuario" | "coach"
    contenido: str
    modalidad: str = "texto"  # texto | voz | imagen
    creado_en: datetime | None = None


def normalizar_hecho(texto: str) -> str:
    """Cuando dos hechos son el mismo hecho: minusculas, sin tildes y sin puntuacion.

    "Prefiere correr por la manana." y "prefiere correr por la mañana" son el mismo
    recuerdo, y guardarlo cinco veces es como se pudre una memoria. Vive en el dominio
    porque es una regla de negocio, no un detalle de como se guarda — la usan tanto el
    repositorio al deduplicar como el caso de uso al decidir si una frase dice algo.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )
    solo_letras = "".join(c if c.isalnum() or c.isspace() else " " for c in sin_tildes)
    return " ".join(solo_letras.split())


@dataclass(frozen=True)
class Hecho:
    """Algo que trasciende la conversacion. Capa 3 (§2).

    La confianza viene del modelo que lo extrajo: no todo lo que se dice de pasada
    merece condicionar un plan.
    """

    categoria: str  # lesion | preferencia | contexto | logro | restriccion
    hecho: str
    confianza: float = 1.0
    vigente: bool = True
    creado_en: datetime | None = None


@dataclass
class TokenAcceso:
    """Token de un solo uso para el enlace magico. Se guarda el hash, nunca el token en claro."""

    id: UUID
    runner_id: UUID
    token_hash: str
    expira_en: datetime
    creado_en: datetime
    ip_solicitud: str | None = None
    usado_en: datetime | None = None

    def esta_vigente(self, ahora: datetime) -> bool:
        return self.usado_en is None and ahora < self.expira_en

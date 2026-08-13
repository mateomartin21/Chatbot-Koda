"""Entidades del dominio. Cero imports externos — ver tests/unit/test_arquitectura.py."""

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

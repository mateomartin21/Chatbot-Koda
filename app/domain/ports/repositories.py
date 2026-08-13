"""Puertos de persistencia. Toda consulta de datos personales exige runner_id o su equivalente
en la firma — ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.1."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.models import Runner, TokenAcceso


class RunnerRepo(ABC):
    @abstractmethod
    async def obtener(self, runner_id: UUID) -> Runner | None: ...

    @abstractmethod
    async def obtener_por_email(self, email: str) -> Runner | None: ...

    @abstractmethod
    async def crear_o_actualizar_acceso(self, email: str) -> Runner:
        """Upsert por email (en minusculas). Si ya existe, actualiza ultimo_acceso."""
        ...


class TokenAccesoRepo(ABC):
    @abstractmethod
    async def crear(
        self, runner_id: UUID, token_hash: str, expira_en: datetime, ip_solicitud: str | None
    ) -> TokenAcceso: ...

    @abstractmethod
    async def obtener_por_hash(self, token_hash: str) -> TokenAcceso | None: ...

    @abstractmethod
    async def marcar_usado(self, token_id: UUID, usado_en: datetime) -> None: ...

    @abstractmethod
    async def contar_creados_desde(
        self, desde: datetime, runner_id: UUID | None = None, ip_solicitud: str | None = None
    ) -> int:
        """Para el rate limit de docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §3."""
        ...

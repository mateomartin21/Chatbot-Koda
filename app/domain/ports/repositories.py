"""Puertos de persistencia. Toda consulta de datos personales exige runner_id o su equivalente
en la firma — ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.1."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from uuid import UUID

from app.domain.models import DatosPerfil, Runner, TokenAcceso
from app.domain.training.modelos import Objetivo, PlanActivo, PlanEntrenamiento, SesionProgramada


class RunnerRepo(ABC):
    @abstractmethod
    async def obtener(self, runner_id: UUID) -> Runner | None: ...

    @abstractmethod
    async def obtener_por_email(self, email: str) -> Runner | None: ...

    @abstractmethod
    async def crear_o_actualizar_acceso(self, email: str) -> Runner:
        """Upsert por email (en minusculas). Si ya existe, actualiza ultimo_acceso."""
        ...

    @abstractmethod
    async def actualizar_perfil(self, runner_id: UUID, datos: DatosPerfil) -> Runner:
        """Actualiza solo los campos que vienen con valor. None = "no me lo has dicho"."""
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


class PlanRepo(ABC):
    """Objetivo, plan y sesiones se guardan y se leen juntos: son un solo agregado.

    runner_id va SIEMPRE en la firma, incluso donde el id del plan bastaria para
    encontrar la fila. Un repositorio que acepta "damelo por su id" es un IDOR
    esperando a que alguien lo llame — ver 03-MULTIUSUARIO-Y-SEGURIDAD.md §4.1.
    """

    @abstractmethod
    async def guardar(
        self,
        runner_id: UUID,
        objetivo: Objetivo,
        plan: PlanEntrenamiento,
        fecha_inicio: date,
    ) -> PlanActivo:
        """Guarda el plan y deja abandonados los objetivos anteriores: solo hay un
        plan activo a la vez. Un runner con dos planes vivos no sabe cual seguir."""
        ...

    @abstractmethod
    async def obtener_activo(self, runner_id: UUID) -> PlanActivo | None: ...

    @abstractmethod
    async def proxima_sesion(self, runner_id: UUID, desde: date) -> SesionProgramada | None: ...

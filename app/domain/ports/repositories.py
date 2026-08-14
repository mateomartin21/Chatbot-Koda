"""Puertos de persistencia. Toda consulta de datos personales exige runner_id o su equivalente
en la firma — ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.1."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date, datetime, time
from uuid import UUID

from app.domain.models import (
    DatosPerfil,
    Hecho,
    Mensaje,
    Recordatorio,
    Runner,
    TipoRecordatorio,
    TokenAcceso,
)
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


class ConversacionRepo(ABC):
    """Capa 2 de la memoria: la ventana corta de docs/contexto/05-MEMORIA.md §2."""

    @abstractmethod
    async def guardar(self, runner_id: UUID, mensajes: Sequence[Mensaje]) -> None: ...

    @abstractmethod
    async def ultimos(self, runner_id: UUID, limite: int = 10) -> list[Mensaje]:
        """Los ultimos turnos en orden cronologico (el mas viejo primero).

        El limite es fijo y no adaptativo a proposito: predecible y de coste constante
        aunque el runner lleve un anio usando la app.
        """
        ...


class MemoriaRepo(ABC):
    """Capa 3: los hechos duraderos (§2)."""

    @abstractmethod
    async def guardar(self, runner_id: UUID, hechos: Sequence[Hecho]) -> int:
        """Guarda los hechos nuevos y devuelve cuantos entraron de verdad.

        Deduplica contra lo que ya hay: 'prefiere correr por la manana' no se guarda
        cinco veces (§4.2). Una memoria que solo acumula se pudre.
        """
        ...

    @abstractmethod
    async def vigentes(self, runner_id: UUID, limite: int = 25) -> list[Hecho]: ...


class RecordatorioRepo(ABC):
    """Cuando escribirle a cada runner.

    activos_de_todos() es la unica consulta del proyecto que cruza usuarios, y es
    deliberada: el scheduler necesita saber a quien programar al arrancar. Devuelve
    la AGENDA (a quien y a que hora), nunca datos personales — esos los vuelve a
    cargar el caso de uso por runner_id cuando toca enviar. Ver
    docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.5.
    """

    @abstractmethod
    async def de_runner(self, runner_id: UUID) -> list[Recordatorio]: ...

    @abstractmethod
    async def guardar(
        self, runner_id: UUID, tipo: TipoRecordatorio, hora_local: time, activo: bool
    ) -> Recordatorio:
        """Crea o actualiza el recordatorio de ese tipo. Uno por tipo y runner."""
        ...

    @abstractmethod
    async def desactivar_todos(self, runner_id: UUID) -> int:
        """La baja. Devuelve cuantos se desactivaron."""
        ...

    @abstractmethod
    async def marcar_enviado(self, runner_id: UUID, tipo: TipoRecordatorio, cuando: datetime) -> None: ...

    @abstractmethod
    async def activos_de_todos(self) -> list[Recordatorio]: ...

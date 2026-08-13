"""Dobles en memoria para tests. Sin red, sin BD — ver docs/contexto/08-CONVENCIONES.md."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.models import Runner, TokenAcceso
from app.domain.ports.repositories import RunnerRepo, TokenAccesoRepo


class InMemoryRunnerRepo(RunnerRepo):
    def __init__(self) -> None:
        self._runners: dict[UUID, Runner] = {}

    async def obtener(self, runner_id: UUID) -> Runner | None:
        return self._runners.get(runner_id)

    async def obtener_por_email(self, email: str) -> Runner | None:
        email = email.lower()
        return next((r for r in self._runners.values() if r.email == email), None)

    async def crear_o_actualizar_acceso(self, email: str) -> Runner:
        email = email.strip().lower()
        existente = await self.obtener_por_email(email)
        ahora = datetime.now(UTC)
        if existente is not None:
            existente.ultimo_acceso = ahora
            return existente
        runner = Runner(id=uuid4(), email=email, creado_en=ahora, ultimo_acceso=ahora)
        self._runners[runner.id] = runner
        return runner

    def agregar(self, runner: Runner) -> None:
        self._runners[runner.id] = runner


class InMemoryTokenAccesoRepo(TokenAccesoRepo):
    def __init__(self) -> None:
        self._tokens: dict[UUID, TokenAcceso] = {}

    async def crear(
        self, runner_id: UUID, token_hash: str, expira_en: datetime, ip_solicitud: str | None
    ) -> TokenAcceso:
        token = TokenAcceso(
            id=uuid4(),
            runner_id=runner_id,
            token_hash=token_hash,
            expira_en=expira_en,
            creado_en=datetime.now(UTC),
            ip_solicitud=ip_solicitud,
        )
        self._tokens[token.id] = token
        return token

    async def obtener_por_hash(self, token_hash: str) -> TokenAcceso | None:
        return next((t for t in self._tokens.values() if t.token_hash == token_hash), None)

    async def marcar_usado(self, token_id: UUID, usado_en: datetime) -> None:
        if token_id in self._tokens:
            self._tokens[token_id].usado_en = usado_en

    async def contar_creados_desde(
        self, desde: datetime, runner_id: UUID | None = None, ip_solicitud: str | None = None
    ) -> int:
        return sum(
            1
            for t in self._tokens.values()
            if t.creado_en >= desde
            and (runner_id is None or t.runner_id == runner_id)
            and (ip_solicitud is None or t.ip_solicitud == ip_solicitud)
        )

    def agregar(self, token: TokenAcceso) -> None:
        self._tokens[token.id] = token

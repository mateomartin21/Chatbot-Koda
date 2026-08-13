"""Implementaciones concretas de los puertos de repositorio, con SQLAlchemy async."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Runner, TokenAcceso
from app.domain.ports.repositories import RunnerRepo, TokenAccesoRepo
from app.infrastructure.persistence.orm import RunnerORM, TokenAccesoORM


def _runner_a_dominio(fila: RunnerORM) -> Runner:
    return Runner(
        id=fila.id,
        email=fila.email,
        creado_en=fila.creado_en,
        activo=fila.activo,
        ultimo_acceso=fila.ultimo_acceso,
        nombre=fila.nombre,
        edad=fila.edad,
        nivel=fila.nivel,
        dias_disponibles=fila.dias_disponibles,
        zona_horaria=fila.zona_horaria,
        marca_distancia_km=fila.marca_distancia_km,
        marca_tiempo_seg=fila.marca_tiempo_seg,
    )


def _token_a_dominio(fila: TokenAccesoORM) -> TokenAcceso:
    return TokenAcceso(
        id=fila.id,
        runner_id=fila.runner_id,
        token_hash=fila.token_hash,
        expira_en=fila.expira_en,
        creado_en=fila.creado_en,
        ip_solicitud=fila.ip_solicitud,
        usado_en=fila.usado_en,
    )


class SqlRunnerRepo(RunnerRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obtener(self, runner_id: UUID) -> Runner | None:
        fila = await self._session.get(RunnerORM, runner_id)
        return _runner_a_dominio(fila) if fila else None

    async def obtener_por_email(self, email: str) -> Runner | None:
        stmt = select(RunnerORM).where(func.lower(RunnerORM.email) == email.lower())
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        return _runner_a_dominio(fila) if fila else None

    async def crear_o_actualizar_acceso(self, email: str) -> Runner:
        email_normalizado = email.lower().strip()
        stmt = select(RunnerORM).where(func.lower(RunnerORM.email) == email_normalizado)
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        ahora = datetime.now(UTC)
        if fila is None:
            fila = RunnerORM(id=uuid4(), email=email_normalizado, ultimo_acceso=ahora)
            self._session.add(fila)
        else:
            fila.ultimo_acceso = ahora
        await self._session.commit()
        await self._session.refresh(fila)
        return _runner_a_dominio(fila)


class SqlTokenAccesoRepo(TokenAccesoRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(
        self, runner_id: UUID, token_hash: str, expira_en: datetime, ip_solicitud: str | None
    ) -> TokenAcceso:
        fila = TokenAccesoORM(
            id=uuid4(),
            runner_id=runner_id,
            token_hash=token_hash,
            expira_en=expira_en,
            ip_solicitud=ip_solicitud,
        )
        self._session.add(fila)
        await self._session.commit()
        await self._session.refresh(fila)
        return _token_a_dominio(fila)

    async def obtener_por_hash(self, token_hash: str) -> TokenAcceso | None:
        stmt = select(TokenAccesoORM).where(TokenAccesoORM.token_hash == token_hash)
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        return _token_a_dominio(fila) if fila else None

    async def marcar_usado(self, token_id: UUID, usado_en: datetime) -> None:
        fila = await self._session.get(TokenAccesoORM, token_id)
        if fila is not None:
            fila.usado_en = usado_en
            await self._session.commit()

    async def contar_creados_desde(
        self, desde: datetime, runner_id: UUID | None = None, ip_solicitud: str | None = None
    ) -> int:
        stmt = select(func.count()).select_from(TokenAccesoORM).where(TokenAccesoORM.creado_en >= desde)
        if runner_id is not None:
            stmt = stmt.where(TokenAccesoORM.runner_id == runner_id)
        if ip_solicitud is not None:
            stmt = stmt.where(TokenAccesoORM.ip_solicitud == ip_solicitud)
        return (await self._session.execute(stmt)).scalar_one()

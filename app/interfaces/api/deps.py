"""Dependencias de FastAPI. get_current_runner() es la UNICA fuente de identidad —
runner_id sale siempre de aqui, nunca del body/query/header. Ver
docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.container import Container, build_container
from app.domain.models import Runner
from app.domain.ports.email_port import EmailPort
from app.domain.ports.repositories import RunnerRepo, TokenAccesoRepo
from app.infrastructure.persistence.repos import SqlRunnerRepo, SqlTokenAccesoRepo

COOKIE_NAME = "koda_session"

_container = build_container()


def get_container() -> Container:
    return _container


def get_settings(container: Container = Depends(get_container)) -> Settings:
    return container.settings


def get_email_port(container: Container = Depends(get_container)) -> EmailPort:
    return container.email


async def get_session(container: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        yield session


@dataclass
class Repos:
    runners: RunnerRepo
    tokens: TokenAccesoRepo


def get_repos(session: AsyncSession = Depends(get_session)) -> Repos:
    return Repos(runners=SqlRunnerRepo(session), tokens=SqlTokenAccesoRepo(session))


def crear_jwt(runner_id: UUID, settings: Settings) -> str:
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(runner_id),
        "iat": ahora,
        "exp": ahora + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def get_current_runner(
    request: Request,
    repos: Repos = Depends(get_repos),
    settings: Settings = Depends(get_settings),
) -> Runner:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "No autenticado")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sesion invalida") from None
    runner = await repos.runners.obtener(UUID(payload["sub"]))
    if runner is None or not runner.activo:
        raise HTTPException(401, "Sesion invalida")
    return runner

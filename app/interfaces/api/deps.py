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
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.repositories import PlanRepo, RunnerRepo, TokenAccesoRepo
from app.domain.ports.stt_port import STTPort
from app.domain.ports.tts_port import TTSPort
from app.domain.ports.voz_realtime_port import VozRealtimePort
from app.infrastructure.persistence.repos import SqlPlanRepo, SqlRunnerRepo, SqlTokenAccesoRepo

COOKIE_NAME = "koda_session"

_container = build_container()


def get_container() -> Container:
    return _container


def get_settings(container: Container = Depends(get_container)) -> Settings:
    return container.settings


def get_email_port(container: Container = Depends(get_container)) -> EmailPort:
    return container.email


def get_stt_port(container: Container = Depends(get_container)) -> STTPort:
    return container.stt


def get_llm_port(container: Container = Depends(get_container)) -> LLMPort:
    return container.llm


def get_tts_port(container: Container = Depends(get_container)) -> TTSPort:
    return container.tts


def get_voz_realtime_port(container: Container = Depends(get_container)) -> VozRealtimePort:
    return container.voz_realtime


def get_coach_system_prompt(container: Container = Depends(get_container)) -> str:
    return container.coach_system_prompt


async def get_session(container: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        yield session


@dataclass
class Repos:
    runners: RunnerRepo
    tokens: TokenAccesoRepo
    planes: PlanRepo


def get_repos(session: AsyncSession = Depends(get_session)) -> Repos:
    return Repos(
        runners=SqlRunnerRepo(session),
        tokens=SqlTokenAccesoRepo(session),
        planes=SqlPlanRepo(session),
    )


def crear_jwt(runner_id: UUID, settings: Settings) -> str:
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(runner_id),
        "iat": ahora,
        "exp": ahora + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def runner_desde_token(token: str | None, repos: Repos, settings: Settings) -> Runner:
    """Compartido entre HTTP (get_current_runner, via cookie de Request) y el
    WebSocket de voz en tiempo real (via cookie del handshake) — misma regla en
    los dos sitios: runner_id sale SIEMPRE de aqui, nunca del cliente."""
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


async def get_current_runner(
    request: Request,
    repos: Repos = Depends(get_repos),
    settings: Settings = Depends(get_settings),
) -> Runner:
    return await runner_desde_token(request.cookies.get(COOKIE_NAME), repos, settings)

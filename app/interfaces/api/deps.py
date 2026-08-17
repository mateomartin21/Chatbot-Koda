"""Dependencias de FastAPI. get_current_runner() es la UNICA fuente de identidad —
runner_id sale siempre de aqui, nunca del body/query/header. Ver
docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.memoria import extraer_y_guardar
from app.config import Settings
from app.container import Container, build_container
from app.domain.models import Mensaje, Runner
from app.domain.ports.email_port import EmailPort
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.moderacion_port import ModeracionImagenPort
from app.domain.ports.repositories import (
    ConversacionRepo,
    MemoriaRepo,
    PlanRepo,
    RecordatorioRepo,
    RunnerRepo,
    TokenAccesoRepo,
)
from app.domain.ports.stt_port import STTPort
from app.domain.ports.tts_port import TTSPort
from app.domain.ports.voz_realtime_port import VozRealtimePort
from app.infrastructure.persistence.repos import (
    SqlConversacionRepo,
    SqlMemoriaRepo,
    SqlPlanRepo,
    SqlRecordatorioRepo,
    SqlRunnerRepo,
    SqlTokenAccesoRepo,
)
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos
from app.interfaces.avisos import crear_ejecutor

COOKIE_NAME = "koda_session"

_container = build_container()


def get_container() -> Container:
    return _container


# El scheduler se crea una sola vez, igual que el contenedor: tiene estado (los avisos
# programados) y crear uno por peticion los perderia.
_scheduler = APSchedulerAvisos(crear_ejecutor(_container))


def get_scheduler() -> APSchedulerAvisos:
    return _scheduler


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


def get_moderacion(container: Container = Depends(get_container)) -> ModeracionImagenPort:
    return container.moderacion


def get_coach_system_prompt(container: Container = Depends(get_container)) -> str:
    return container.coach_system_prompt


def get_coach_voz_prompt(container: Container = Depends(get_container)) -> str:
    return container.coach_voz_prompt


def get_voz_locutor_prompt(container: Container = Depends(get_container)) -> str:
    return container.voz_locutor_prompt


async def get_session(container: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        yield session


@dataclass
class Repos:
    runners: RunnerRepo
    tokens: TokenAccesoRepo
    planes: PlanRepo
    conversaciones: ConversacionRepo
    memoria: MemoriaRepo
    recordatorios: RecordatorioRepo


def get_repos(session: AsyncSession = Depends(get_session)) -> Repos:
    return Repos(
        runners=SqlRunnerRepo(session),
        tokens=SqlTokenAccesoRepo(session),
        planes=SqlPlanRepo(session),
        conversaciones=SqlConversacionRepo(session),
        memoria=SqlMemoriaRepo(session),
        recordatorios=SqlRecordatorioRepo(session),
    )


# Las tareas de fondo se guardan aqui porque asyncio solo mantiene una referencia
# debil: sin esto, el recolector puede matar la extraccion a medias sin avisar.
_tareas_de_fondo: set[asyncio.Task] = set()


def lanzar_extraccion_de_memoria(runner_id: UUID, mensajes: Sequence[Mensaje], container: Container) -> None:
    """Dispara la capa 3 sin bloquear la respuesta (docs/contexto/05-MEMORIA.md §5).

    Abre su PROPIA sesion de base de datos: la de la peticion ya esta cerrada cuando
    esto corre, que es justo el punto de que no este en el camino critico.
    """

    async def _tarea() -> None:
        async with container.session_factory() as session:
            await extraer_y_guardar(
                runner_id,
                mensajes,
                SqlMemoriaRepo(session),
                container.llm_barato,
                container.prompt_extraccion_memoria,
            )

    tarea = asyncio.create_task(_tarea())
    _tareas_de_fondo.add(tarea)
    tarea.add_done_callback(_tareas_de_fondo.discard)


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

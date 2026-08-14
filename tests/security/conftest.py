import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.interfaces.api import deps
from app.main import app
from tests.fakes.email import FakeEmail
from tests.fakes.repos import (
    InMemoryConversacionRepo,
    InMemoryMemoriaRepo,
    InMemoryPlanRepo,
    InMemoryRunnerRepo,
    InMemoryTokenAccesoRepo,
)


@pytest_asyncio.fixture
async def repos() -> deps.Repos:
    return deps.Repos(
        runners=InMemoryRunnerRepo(),
        tokens=InMemoryTokenAccesoRepo(),
        planes=InMemoryPlanRepo(),
        conversaciones=InMemoryConversacionRepo(),
        memoria=InMemoryMemoriaRepo(),
    )


@pytest_asyncio.fixture
async def email_fake() -> FakeEmail:
    return FakeEmail()


@pytest_asyncio.fixture
async def cliente(repos: deps.Repos, email_fake: FakeEmail):
    app.dependency_overrides[deps.get_repos] = lambda: repos
    app.dependency_overrides[deps.get_email_port] = lambda: email_fake
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def runner_a(repos: deps.Repos):
    return await repos.runners.crear_o_actualizar_acceso("runnera@example.com")


@pytest_asyncio.fixture
async def runner_b(repos: deps.Repos):
    return await repos.runners.crear_o_actualizar_acceso("runnerb@example.com")


async def _crear_token(repos: deps.Repos, runner_id, minutos_para_expirar: int) -> str:
    token_claro = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_claro.encode()).hexdigest()
    expira_en = datetime.now(UTC) + timedelta(minutes=minutos_para_expirar)
    await repos.tokens.crear(runner_id, token_hash, expira_en, "127.0.0.1")
    return token_claro


@pytest_asyncio.fixture
async def token(repos: deps.Repos, runner_a) -> str:
    return await _crear_token(repos, runner_a.id, minutos_para_expirar=15)


@pytest_asyncio.fixture
async def token_expirado(repos: deps.Repos, runner_a) -> str:
    return await _crear_token(repos, runner_a.id, minutos_para_expirar=-1)

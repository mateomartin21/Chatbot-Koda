"""Composition root. El UNICO archivo que sabe que adaptador concreto se usa
para cada puerto — ver docs/contexto/01-ARQUITECTURA.md."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.domain.ports.email_port import EmailPort
from app.infrastructure.email.ses import SESEmail
from app.infrastructure.persistence.db import crear_session_factory


@dataclass
class Container:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    email: EmailPort


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()

    # Plan B (docs/contexto/00-CONTEXTO.md): cuando exista ResendEmail, este es el
    # unico "if" que cambia segun settings.provider_email. Hoy solo hay adaptador AWS.
    email: EmailPort = SESEmail(settings)

    return Container(
        settings=settings,
        session_factory=crear_session_factory(settings),
        email=email,
    )

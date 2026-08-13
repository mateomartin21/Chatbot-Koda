"""Composition root. El UNICO archivo que sabe que adaptador concreto se usa
para cada puerto — ver docs/contexto/01-ARQUITECTURA.md."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.domain.ports.email_port import EmailPort
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.stt_port import STTPort
from app.domain.ports.tts_port import TTSPort
from app.infrastructure.email.ses import SESEmail
from app.infrastructure.llm.bedrock_converse import BedrockConverse
from app.infrastructure.llm.groq_llm import GroqLLM
from app.infrastructure.llm.model_gateway import ModelGatewayLLM
from app.infrastructure.persistence.db import crear_session_factory
from app.infrastructure.stt.groq_whisper import GroqWhisperSTT
from app.infrastructure.stt.transcribe_aws import TranscribeAWS
from app.infrastructure.tts.polly import PollyTTS

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class Container:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    email: EmailPort
    stt: STTPort
    llm: LLMPort
    tts: TTSPort
    coach_system_prompt: str


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()

    # Plan B (docs/contexto/00-CONTEXTO.md): cuando exista ResendEmail, este es el
    # unico "if" que cambia segun settings.provider_email. Hoy solo hay adaptador AWS.
    email: EmailPort = SESEmail(settings)

    # STT en "fallback" desde 2026-08-14: Transcribe bloqueado por cuenta nueva.
    # Ver docs/adr/ADR-009-groq-stt-temporal.md. Volver a "aws" es cambiar esta linea.
    stt: STTPort = TranscribeAWS(settings) if settings.provider_stt == "aws" else GroqWhisperSTT(settings)

    # Gateway de modelos: cadena ordenada de proveedores, no un reintento de la misma
    # llamada. Los tiers barato/Groq son opcionales — si no estan configurados, el
    # gateway sigue funcionando solo con el modelo principal de Bedrock.
    tiers_llm: list[LLMPort] = [BedrockConverse(settings, settings.bedrock_model_id)]
    if settings.bedrock_model_id_barato:
        tiers_llm.append(BedrockConverse(settings, settings.bedrock_model_id_barato))
    if settings.groq_api_key:
        tiers_llm.append(GroqLLM(settings))
    llm: LLMPort = ModelGatewayLLM(tiers_llm)

    tts: TTSPort = PollyTTS(settings)

    coach_system_prompt = (_PROMPTS_DIR / "coach_system.md").read_text(encoding="utf-8")

    return Container(
        settings=settings,
        session_factory=crear_session_factory(settings),
        email=email,
        stt=stt,
        llm=llm,
        tts=tts,
        coach_system_prompt=coach_system_prompt,
    )

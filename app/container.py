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
from app.domain.ports.voz_realtime_port import VozRealtimePort
from app.infrastructure.email.ses import SESEmail
from app.infrastructure.llm.bedrock_converse import BedrockConverse
from app.infrastructure.llm.groq_llm import GroqLLM
from app.infrastructure.llm.model_gateway import ModelGatewayLLM
from app.infrastructure.persistence.db import crear_session_factory
from app.infrastructure.stt.groq_whisper import GroqWhisperSTT
from app.infrastructure.stt.transcribe_aws import TranscribeAWS
from app.infrastructure.tts.polly import PollyTTS
from app.infrastructure.voz_realtime.nova_sonic import NovaSonicRealtime

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PLANTILLAS_DIR = Path(__file__).parent / "infrastructure" / "email" / "plantillas"


@dataclass
class Container:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    email: EmailPort
    stt: STTPort
    llm: LLMPort
    tts: TTSPort
    voz_realtime: VozRealtimePort
    # Modelo pequeno para la extraccion de memoria: es clasificacion, no razonamiento
    # (docs/contexto/05-MEMORIA.md §5). Va aparte del gateway a proposito — aqui no
    # interesa la calidad del tier 1, interesa que sea barato.
    llm_barato: LLMPort
    coach_system_prompt: str
    # Nova Sonic recibe un prompt aparte, mucho mas corto. No es duplicacion por
    # descuido: ver el comentario de build_container.
    coach_voz_prompt: str
    prompt_extraccion_memoria: str
    plantilla_recordatorio: str


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()

    # Plan B (docs/contexto/00-CONTEXTO.md): cuando exista ResendEmail, este es el
    # unico "if" que cambia segun settings.provider_email. Hoy solo hay adaptador AWS.
    email: EmailPort = SESEmail(settings)

    # STT en "fallback" desde 2026-08-14: Transcribe bloqueado por cuenta nueva.
    # Ver docs/adr/ADR-009-groq-stt-temporal.md. Volver a "aws" es cambiar esta linea.
    stt: STTPort = TranscribeAWS(settings) if settings.provider_stt == "aws" else GroqWhisperSTT(settings)

    # Gateway de modelos (docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md): cadena
    # ordenada de proveedores, no un reintento de la misma llamada. Los tiers barato/Groq
    # son opcionales — si no estan configurados, el gateway sigue funcionando solo con
    # el modelo principal de Bedrock.
    tiers_llm: list[LLMPort] = [BedrockConverse(settings, settings.bedrock_model_id)]
    if settings.bedrock_model_id_barato:
        tiers_llm.append(BedrockConverse(settings, settings.bedrock_model_id_barato))
    if settings.groq_api_key:
        tiers_llm.append(GroqLLM(settings))
    llm: LLMPort = ModelGatewayLLM(tiers_llm)

    # Si no hay modelo barato configurado, la extraccion usa el gateway completo: mas
    # cara, pero mejor que quedarse sin memoria por una variable de entorno vacia.
    llm_barato: LLMPort = (
        BedrockConverse(settings, settings.bedrock_model_id_barato)
        if settings.bedrock_model_id_barato
        else llm
    )

    tts: TTSPort = PollyTTS(settings)

    # Nivel 0 del pipeline de voz (docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md):
    # audio en tiempo real. Si falla al abrir sesion o a media conversacion, el frontend
    # cae al endpoint POST /api/mensajes de siempre (STT+LLM gateway+TTS de arriba).
    voz_realtime: VozRealtimePort = NovaSonicRealtime(settings)

    coach_system_prompt = (_PROMPTS_DIR / "coach_system.md").read_text(encoding="utf-8")

    # Dos prompts para el mismo coach, a proposito. coach_system.md son ~2.800
    # caracteres escritos para un modelo grande; con esa longitud Nova Sonic ignoraba
    # instrucciones explicitas (preguntaba el anio teniendo la fecha de hoy delante,
    # y volvia a pedir datos del perfil que tenia justo encima). Es un modelo pequeno
    # optimizado para latencia y su seguimiento de instrucciones se degrada con la
    # longitud. coach_voz.md dice lo mismo en un tercio del espacio.
    coach_voz_prompt = (_PROMPTS_DIR / "coach_voz.md").read_text(encoding="utf-8")
    prompt_extraccion_memoria = (_PROMPTS_DIR / "extraccion_memoria.md").read_text(encoding="utf-8")
    plantilla_recordatorio = (_PLANTILLAS_DIR / "recordatorio.html").read_text(encoding="utf-8")

    return Container(
        settings=settings,
        session_factory=crear_session_factory(settings),
        email=email,
        stt=stt,
        llm=llm,
        tts=tts,
        voz_realtime=voz_realtime,
        llm_barato=llm_barato,
        coach_system_prompt=coach_system_prompt,
        coach_voz_prompt=coach_voz_prompt,
        prompt_extraccion_memoria=prompt_extraccion_memoria,
        plantilla_recordatorio=plantilla_recordatorio,
    )

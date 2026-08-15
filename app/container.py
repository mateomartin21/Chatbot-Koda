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
from app.infrastructure.email.smtp import SMTPEmail
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
    # El coach cuando la peticion viene por voz: las reglas de siempre mas las de
    # hablar, porque su respuesta se va a leer en alto. No es duplicacion por
    # descuido: ver el comentario de build_container.
    coach_voz_prompt: str
    # Lo unico que oye Nova Sonic. No contiene un solo dato del runner, y eso es la
    # garantia — ver docs/adr/ADR-020-nova-habla-y-sonnet-decide.md.
    voz_locutor_prompt: str
    prompt_extraccion_memoria: str
    plantilla_recordatorio: str


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()

    # PROVIDER_EMAIL=smtp es el plan B mientras SES siga en sandbox — donde solo
    # entrega a direcciones verificadas a mano, es decir, a nadie que no conozcas de
    # antemano. Ver docs/adr/ADR-022-el-correo-tiene-que-llegar-a-cualquiera.md.
    email: EmailPort = SESEmail(settings) if settings.provider_email == "aws" else SMTPEmail(settings)

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

    # Tres prompts, y cada uno es para un papel distinto:
    #
    # - coach_system.md  el coach por escrito. ~2.800 caracteres para un modelo grande.
    # - coach_voz.md     el mismo coach cuando la peticion llega hablando: mismas
    #                    herramientas y mismo dominio, pero respuestas cortas y sin
    #                    markdown, porque lo que diga se va a leer en voz alta.
    # - voz_locutor.md   Nova Sonic. Ni herramientas del coach ni datos del runner:
    #                    solo como hablar y la orden de consultarlo todo. Es lo que
    #                    hace imposible que se invente un ritmo — no tiene ninguno.
    #
    # El reparto no es capricho: con coach_system.md entero, Nova Sonic ignoraba
    # instrucciones explicitas (preguntaba el anio teniendo la fecha delante, y volvia
    # a pedir datos del perfil que tenia justo encima). Es un modelo pequeno optimizado
    # para latencia y su seguimiento de instrucciones se degrada con la longitud.
    coach_voz_prompt = (_PROMPTS_DIR / "coach_voz.md").read_text(encoding="utf-8")
    voz_locutor_prompt = (_PROMPTS_DIR / "voz_locutor.md").read_text(encoding="utf-8")
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
        voz_locutor_prompt=voz_locutor_prompt,
        prompt_extraccion_memoria=prompt_extraccion_memoria,
        plantilla_recordatorio=plantilla_recordatorio,
    )

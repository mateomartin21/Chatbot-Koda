"""Caso de uso central: une STT, LLM y TTS. Voz y texto desde el principio.

El manejo de errores sigue la tabla de degradacion de docs/contexto/01-ARQUITECTURA.md:
que falte STT o TTS es molesto, que la app se caiga es descalificante. Por eso se
capturan excepciones genericas aqui — es la frontera que traduce fallos de
infraestructura (boto3, httpx...) en una respuesta conversacional, sin acoplar la
capa de aplicacion a tipos de excepcion concretos de un SDK.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, Imagen, LLMPort
from app.domain.ports.stt_port import STTPort
from app.domain.ports.tts_port import TTSPort

_MENSAJE_NO_ESCUCHE = "No te escuché bien, ¿lo repites?"
_MENSAJE_LLM_CAIDO = "Se me complicó pensar la respuesta justo ahora. ¿Me lo repites en un momento?"
# Una foto sin texto es una peticion completa: "mira esto". Se le pone palabras
# aqui para que el turno que llega al modelo siempre tenga una intencion escrita.
_FOTO_SIN_TEXTO = "Te mando una foto."
_MENSAJE_MODELO_CIEGO = (
    "Ahora mismo no puedo mirar fotos. Si me dices los kilómetros y el tiempo, lo apunto igual."
)


@dataclass
class RespuestaCoach:
    texto: str
    audio: bytes | None  # None si Polly fallo — la conversacion sigue solo en texto
    # Lo que dijo el usuario. Si vino por voz es la transcripcion, que es lo unico que
    # tiene sentido guardar en la memoria: nadie relee un WAV.
    texto_usuario: str = ""


async def procesar_mensaje(
    *,
    texto: str | None,
    audio: bytes | None,
    audio_mime: str | None,
    stt: STTPort,
    llm: LLMPort,
    tts: TTSPort,
    system_prompt: str,
    herramientas: Sequence[Herramienta] = (),
    ejecutar: EjecutorHerramientas | None = None,
    imagen: Imagen | None = None,
) -> RespuestaCoach:
    if texto and texto.strip():
        texto_usuario = texto.strip()
    elif imagen is not None and audio is None:
        texto_usuario = _FOTO_SIN_TEXTO
    else:
        if audio is None or audio_mime is None:
            return RespuestaCoach(texto=_MENSAJE_NO_ESCUCHE, audio=None)
        try:
            texto_usuario = (await stt.transcribir(audio, audio_mime)).strip()
        except Exception:  # noqa: BLE001 — degradar, no morir (ver docstring)
            return RespuestaCoach(texto=_MENSAJE_NO_ESCUCHE, audio=None)
        if not texto_usuario:
            return RespuestaCoach(texto=_MENSAJE_NO_ESCUCHE, audio=None)

    # Si hay foto y ningun modelo disponible sabe ver, se dice — no se contesta como
    # si se hubiera mirado. Ese es el fallo que deja al runner creyendo que su
    # entrenamiento quedo apuntado cuando nadie ha leido nada.
    if imagen is not None and not llm.soporta_imagenes:
        return RespuestaCoach(texto=_MENSAJE_MODELO_CIEGO, audio=None, texto_usuario=texto_usuario)

    try:
        texto_respuesta = await llm.conversar(
            texto_usuario,
            system_prompt=system_prompt,
            herramientas=herramientas,
            ejecutar=ejecutar,
            imagen=imagen,
        )
    except Exception:  # noqa: BLE001 — el LLM (ahora un gateway con fallback entre
        # proveedores, ver model_gateway.py) ya agoto sus propios tiers. Si llega aqui,
        # no queda mas que degradar a un mensaje amable.
        texto_respuesta = _MENSAJE_LLM_CAIDO

    try:
        audio_respuesta = await tts.sintetizar(texto_respuesta)
    except Exception:  # noqa: BLE001
        audio_respuesta = None

    return RespuestaCoach(texto=texto_respuesta, audio=audio_respuesta, texto_usuario=texto_usuario)

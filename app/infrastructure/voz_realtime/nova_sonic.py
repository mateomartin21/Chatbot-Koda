"""Adaptador de VozRealtimePort sobre Amazon Nova 2 Sonic (audio a audio, tiempo real).

OJO, distinto al resto de infrastructure/: esto NO usa boto3. Nova Sonic se invoca con
InvokeModelWithBidirectionalStream, que boto3 todavia no soporta — hace falta el SDK
async aparte aws_sdk_bedrock_runtime + smithy_aws_core (ambos pre-1.0). Ver
docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md para el porque de esta dependencia
extra y sus riesgos.

Sigue el patron del sample oficial de AWS (SimpleNovaSonic):
https://github.com/aws-samples/amazon-nova-samples/tree/main/speech-to-speech/amazon-nova-2-sonic
"""

import asyncio
import base64
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from aws_sdk_bedrock_runtime.client import (
    AsyncBedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.config import Config
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
)
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

from app.config import Settings
from app.domain.ports.voz_realtime_port import (
    ErrorSesion,
    EventoVoz,
    FragmentoAudio,
    SesionVozRealtime,
    TranscripcionParcial,
    TurnoTerminado,
    VozRealtimePort,
)
from app.infrastructure.aws_session import exportar_credenciales_a_entorno

logger = logging.getLogger(__name__)

_MODEL_ID = "amazon.nova-2-sonic-v1:0"
# "matthew" (voz por defecto de los samples de AWS) es una voz en ingles -- sonaba
# inconsistente con Polly (voz "Mia", espanol) en la cascada. Nova Sonic solo ofrece
# es-US por ahora (no es-MX): "lupe" (femenina) y "carlos" (masculina). "lupe" para
# quedar mas cerca de Mia.
_VOZ = "lupe"

# Nova Sonic no manda "completionEnd" de forma fiable en la practica (SDK/modelo
# pre-1.0) -- en su lugar suele mandar VARIOS bloques de audio/texto con huecos reales
# de varios segundos entre ellos mientras genera. Un timeout de inactividad corto (ej.
# 2.5s) corta el audio a media respuesta -- lo confirmamos en pruebas reales. En vez de
# adivinar por silencio, se usa la senal real: el contentEnd del bloque de AUDIO con
# stopReason=END_TURN indica que el audio de verdad termino. Desde ahi se da un margen
# corto para el texto final que pueda venir despues, y recien ahi se cierra. El timeout
# largo sigue existiendo como red de seguridad genuina para una sesion sin ninguna
# respuesta (el caso del "segundo hola" que nunca contesto nada).
_TIMEOUT_INACTIVIDAD_SEGUNDOS = 10.0
_TIMEOUT_CIERRE_SEGUNDOS = 2.5

# Nova Sonic necesita un flujo de audio CONTINUO para seguir respondiendo, aunque la
# entrada del turno sea texto. El sample oficial de AWS resuelve esto con un
# "SilentAudioStreamer" que manda PCM en silencio mientras dura el modo texto; sin eso
# la sesion se queda inerte y solo devuelve usageEvent, sin ninguna respuesta
# (verificado en pruebas reales). Mismos valores que el sample: 1024 muestras de 16
# bits cada 10ms.
_TAM_CHUNK_SILENCIO = 2048
_PAUSA_SILENCIO_SEGUNDOS = 0.01


class NovaSonicSesion(SesionVozRealtime):
    def __init__(self, client: AsyncBedrockRuntimeClient, model_id: str) -> None:
        self._client = client
        self._model_id = model_id
        self._prompt_name = str(uuid.uuid4())
        self._content_name_sistema = str(uuid.uuid4())
        self._content_name_audio = str(uuid.uuid4())
        self._stream = None
        self._activa = False
        self._audio_iniciado = False
        self._tarea_silencio: asyncio.Task | None = None
        # El stream de entrada es uno solo: si el turno de texto y su audio de silencio
        # mandan eventos a la vez, hay que serializarlos.
        self._lock_envio = asyncio.Lock()

    async def abrir(self, system_prompt: str) -> None:
        self._stream = await self._client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self._model_id)
        )
        self._activa = True
        await self._enviar_evento(
            {
                "event": {
                    "sessionStart": {
                        "inferenceConfiguration": {"maxTokens": 1024, "topP": 0.9, "temperature": 0.7}
                    }
                }
            }
        )
        await self._enviar_evento(
            {
                "event": {
                    "promptStart": {
                        "promptName": self._prompt_name,
                        "textOutputConfiguration": {"mediaType": "text/plain"},
                        "audioOutputConfiguration": {
                            "mediaType": "audio/lpcm",
                            "sampleRateHertz": 24000,
                            "sampleSizeBits": 16,
                            "channelCount": 1,
                            "voiceId": _VOZ,
                            "encoding": "base64",
                            "audioType": "SPEECH",
                        },
                    }
                }
            }
        )
        await self._enviar_evento(
            {
                "event": {
                    "contentStart": {
                        "promptName": self._prompt_name,
                        "contentName": self._content_name_sistema,
                        "type": "TEXT",
                        "interactive": False,
                        "role": "SYSTEM",
                        "textInputConfiguration": {"mediaType": "text/plain"},
                    }
                }
            }
        )
        await self._enviar_evento(
            {
                "event": {
                    "textInput": {
                        "promptName": self._prompt_name,
                        "contentName": self._content_name_sistema,
                        "content": system_prompt,
                    }
                }
            }
        )
        await self._enviar_evento(
            {
                "event": {
                    "contentEnd": {
                        "promptName": self._prompt_name,
                        "contentName": self._content_name_sistema,
                    }
                }
            }
        )

    async def _enviar_evento(self, evento: dict) -> None:
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=json.dumps(evento).encode("utf-8"))
        )
        async with self._lock_envio:
            await self._stream.input_stream.send(chunk)

    async def _abrir_bloque_audio(self) -> None:
        if self._audio_iniciado:
            return
        await self._enviar_evento(
            {
                "event": {
                    "contentStart": {
                        "promptName": self._prompt_name,
                        "contentName": self._content_name_audio,
                        "type": "AUDIO",
                        "interactive": True,
                        "role": "USER",
                        "audioInputConfiguration": {
                            "mediaType": "audio/lpcm",
                            "sampleRateHertz": 16000,
                            "sampleSizeBits": 16,
                            "channelCount": 1,
                            "audioType": "SPEECH",
                            "encoding": "base64",
                        },
                    }
                }
            }
        )
        self._audio_iniciado = True

    async def _enviar_chunk_audio(self, chunk: bytes) -> None:
        await self._enviar_evento(
            {
                "event": {
                    "audioInput": {
                        "promptName": self._prompt_name,
                        "contentName": self._content_name_audio,
                        "content": base64.b64encode(chunk).decode("utf-8"),
                    }
                }
            }
        )

    async def enviar_audio(self, chunk: bytes) -> None:
        if not self._activa:
            return
        await self._abrir_bloque_audio()
        await self._enviar_chunk_audio(chunk)

    async def _enviar_silencio(self) -> None:
        """Mantiene viva la sesion en modo texto — ver comentario de _TAM_CHUNK_SILENCIO."""
        silencio = b"\x00" * _TAM_CHUNK_SILENCIO
        try:
            while self._activa:
                await self._enviar_chunk_audio(silencio)
                await asyncio.sleep(_PAUSA_SILENCIO_SEGUNDOS)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — la sesion ya se esta cayendo
            logger.info("Se detuvo el audio de silencio: %s", error)

    async def enviar_texto(self, texto: str) -> None:
        # El audio de silencio tiene que estar corriendo ANTES de mandar el texto, si no
        # Nova Sonic no genera respuesta (ver _TAM_CHUNK_SILENCIO).
        await self._abrir_bloque_audio()
        if self._tarea_silencio is None:
            self._tarea_silencio = asyncio.create_task(self._enviar_silencio())
            await asyncio.sleep(0.1)  # margen para que el flujo quede establecido

        content_name = str(uuid.uuid4())
        await self._enviar_evento(
            {
                "event": {
                    "contentStart": {
                        "promptName": self._prompt_name,
                        "contentName": content_name,
                        "type": "TEXT",
                        "interactive": True,
                        "role": "USER",
                        "textInputConfiguration": {"mediaType": "text/plain"},
                    }
                }
            }
        )
        await self._enviar_evento(
            {
                "event": {
                    "textInput": {
                        "promptName": self._prompt_name,
                        "contentName": content_name,
                        "content": texto,
                    }
                }
            }
        )
        await self._enviar_evento(
            {"event": {"contentEnd": {"promptName": self._prompt_name, "contentName": content_name}}}
        )

    async def terminar_turno_audio(self) -> None:
        if not self._audio_iniciado:
            return
        await self._enviar_evento(
            {
                "event": {
                    "contentEnd": {
                        "promptName": self._prompt_name,
                        "contentName": self._content_name_audio,
                    }
                }
            }
        )
        self._audio_iniciado = False

    async def _recibir_un_resultado(self):
        output = await self._stream.await_output()
        return await output[1].receive()

    async def eventos(self) -> AsyncIterator[EventoVoz]:
        # Nova Sonic manda el texto de la respuesta en varios bloques por turno: uno o
        # mas previews (generationStage=SPECULATIVE, a veces solo un fragmento corto) y
        # despues, frase por frase, la transcripcion FINAL confirmada de lo que de verdad
        # se dijo. El preview puede llegar incompleto -- nos quedamos con los bloques
        # FINAL, que juntos reconstruyen la respuesta completa y real.
        # El fin de turno documentado es "completionEnd", pero en la practica no siempre
        # llega (SDK/modelo pre-1.0, comportamiento no coincide del todo con la doc) --
        # si Nova Sonic se queda callado un rato, se asume que el turno termino.
        # https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-output-events.html
        rol_actual = "coach"
        etapa_actual = None
        # Plazo real (no "silencio del stream"): en modo texto mandamos audio de silencio
        # continuo, asi que llegan usageEvent todo el tiempo y un timeout de recepcion
        # nunca se disparia. Con un deadline explicito el turno cierra igual.
        deadline_cierre: float | None = None
        try:
            while self._activa:
                timeout = _TIMEOUT_INACTIVIDAD_SEGUNDOS
                if deadline_cierre is not None:
                    restante = deadline_cierre - time.monotonic()
                    if restante <= 0:
                        logger.info("Margen tras END_TURN agotado, turno terminado")
                        yield TurnoTerminado()
                        return
                    timeout = min(restante, _TIMEOUT_INACTIVIDAD_SEGUNDOS)
                try:
                    resultado = await asyncio.wait_for(self._recibir_un_resultado(), timeout=timeout)
                except TimeoutError:
                    logger.info("Sin eventos nuevos por %.1fs, se asume turno terminado", timeout)
                    yield TurnoTerminado()
                    return
                if not (resultado.value and resultado.value.bytes_):
                    continue
                datos = json.loads(resultado.value.bytes_.decode("utf-8"))
                evento = datos.get("event", {})
                if "contentStart" in evento:
                    inicio = evento["contentStart"]
                    rol_actual = "coach" if inicio.get("role") == "ASSISTANT" else "usuario"
                    campos = inicio.get("additionalModelFields")
                    etapa_actual = json.loads(campos).get("generationStage") if campos else None
                    if inicio.get("type") == "AUDIO":
                        deadline_cierre = None  # llego mas audio, el turno sigue vivo
                    logger.info(
                        "contentStart role=%s type=%s stage=%s contentId=%s",
                        inicio.get("role"),
                        inicio.get("type"),
                        etapa_actual,
                        inicio.get("contentId"),
                    )
                elif "textOutput" in evento:
                    texto = evento["textOutput"]["content"]
                    # Se reenvian las dos etapas: el adelanto para que el texto aparezca
                    # junto con el audio, y la definitiva para corregirlo. Filtrar solo
                    # una de las dos deja el chat mudo cuando esa no llega — pasa de
                    # verdad, sobre todo en turnos de voz.
                    definitiva = etapa_actual != "SPECULATIVE"
                    logger.info(
                        "textOutput rol=%s stage=%s definitiva=%s texto=%r",
                        rol_actual,
                        etapa_actual,
                        definitiva,
                        texto,
                    )
                    if deadline_cierre is not None:
                        # La transcripcion confirmada llega frase por frase DESPUES del
                        # fin del audio. Mientras siga llegando texto, se estira el
                        # margen: si no, el mensaje se corta a la mitad.
                        deadline_cierre = time.monotonic() + _TIMEOUT_CIERRE_SEGUNDOS
                    yield TranscripcionParcial(texto=texto, rol=rol_actual, definitiva=definitiva)
                elif "audioOutput" in evento:
                    audio = base64.b64decode(evento["audioOutput"]["content"])
                    logger.debug("audioOutput %d bytes", len(audio))
                    yield FragmentoAudio(datos=audio)
                elif "contentEnd" in evento:
                    fin = evento["contentEnd"]
                    logger.info("contentEnd type=%s stopReason=%s", fin.get("type"), fin.get("stopReason"))
                    if fin.get("type") == "AUDIO" and fin.get("stopReason") == "END_TURN":
                        # Senal real de que el audio de la respuesta ya termino -- desde
                        # aqui solo esperamos un poco por si llega texto final rezagado.
                        deadline_cierre = time.monotonic() + _TIMEOUT_CIERRE_SEGUNDOS
                elif "completionEnd" in evento:
                    logger.info("completionEnd stopReason=%s", evento["completionEnd"].get("stopReason"))
                    yield TurnoTerminado()
                    return
                else:
                    logger.info("evento sin manejar: %s", list(evento.keys()))
        except Exception as error:
            # Cualquier fallo del stream se traduce a un evento de error; el endpoint WS
            # lo usa para disparar el fallback a la cascada. Se loguea para diagnosticar.
            logger.warning("Sesion de Nova Sonic interrumpida: %s", error, exc_info=True)
            yield ErrorSesion(mensaje=str(error))

    async def cerrar(self) -> None:
        if not self._activa:
            return
        self._activa = False
        if self._tarea_silencio is not None:
            self._tarea_silencio.cancel()
            self._tarea_silencio = None
        try:
            await self._enviar_evento({"event": {"promptEnd": {"promptName": self._prompt_name}}})
            await self._enviar_evento({"event": {"sessionEnd": {}}})
            await self._stream.input_stream.close()
        except Exception:  # noqa: BLE001 — cerrar es best-effort, no debe tumbar el endpoint
            pass


class NovaSonicRealtime(VozRealtimePort):
    def __init__(self, settings: Settings, model_id: str = _MODEL_ID) -> None:
        exportar_credenciales_a_entorno(settings)
        self._region = settings.aws_region
        self._model_id = model_id
        self._client: AsyncBedrockRuntimeClient | None = None

    def _cliente(self) -> AsyncBedrockRuntimeClient:
        if self._client is None:
            config = Config(
                endpoint_uri=f"https://bedrock-runtime.{self._region}.amazonaws.com",
                region=self._region,
                aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            )
            self._client = AsyncBedrockRuntimeClient(config=config)
        return self._client

    async def abrir_sesion(self, *, system_prompt: str) -> SesionVozRealtime:
        sesion = NovaSonicSesion(self._cliente(), self._model_id)
        await sesion.abrir(system_prompt)
        return sesion

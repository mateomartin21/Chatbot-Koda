"""POST /api/mensajes — el endpoint central. runner_id sale SIEMPRE de get_current_runner(),
nunca del formulario. Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2."""

import base64

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.application.coach import HERRAMIENTAS, ejecutor_para
from app.application.contexto import ReposDelCoach, construir_contexto, construir_system_prompt
from app.application.procesar_mensaje import procesar_mensaje
from app.container import Container
from app.domain.models import Mensaje, Runner
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.stt_port import STTPort
from app.domain.ports.tts_port import TTSPort
from app.interfaces.api.deps import (
    Repos,
    get_coach_system_prompt,
    get_container,
    get_current_runner,
    get_llm_port,
    get_repos,
    get_stt_port,
    get_tts_port,
    lanzar_extraccion_de_memoria,
)

router = APIRouter(prefix="/api", tags=["mensajes"])


class MensajeRespuesta(BaseModel):
    texto: str
    audio_base64: str | None


@router.post("/mensajes", response_model=MensajeRespuesta)
async def enviar_mensaje(
    runner: Runner = Depends(get_current_runner),
    texto: str | None = Form(None),
    audio: UploadFile | None = File(None),
    stt: STTPort = Depends(get_stt_port),
    llm: LLMPort = Depends(get_llm_port),
    tts: TTSPort = Depends(get_tts_port),
    system_prompt: str = Depends(get_coach_system_prompt),
    repos: Repos = Depends(get_repos),
    container: Container = Depends(get_container),
) -> MensajeRespuesta:
    audio_bytes = await audio.read() if audio is not None else None
    audio_mime = audio.content_type if audio is not None else None

    repos_coach = ReposDelCoach(
        runners=repos.runners,
        planes=repos.planes,
        conversaciones=repos.conversaciones,
        memoria=repos.memoria,
    )
    contexto = await construir_contexto(runner, repos_coach)
    respuesta = await procesar_mensaje(
        texto=texto,
        audio=audio_bytes,
        audio_mime=audio_mime,
        stt=stt,
        llm=llm,
        tts=tts,
        system_prompt=construir_system_prompt(system_prompt, contexto),
        herramientas=HERRAMIENTAS,
        # El ejecutor se ata al runner del JWT: el modelo elige QUE herramienta, nunca
        # sobre quien. Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2.
        ejecutar=ejecutor_para(runner, repos_coach),
    )

    # El turno se guarda DESPUES de responder: la memoria no puede estar en el camino
    # critico de la latencia. Si esto fallara, el runner ya tiene su respuesta.
    modalidad = "voz" if audio_bytes else "texto"
    turno = [
        Mensaje(rol="usuario", contenido=respuesta.texto_usuario, modalidad=modalidad),
        Mensaje(rol="coach", contenido=respuesta.texto, modalidad=modalidad),
    ]
    await repos.conversaciones.guardar(runner.id, turno)
    lanzar_extraccion_de_memoria(runner.id, turno, container)

    audio_base64 = base64.b64encode(respuesta.audio).decode() if respuesta.audio else None
    return MensajeRespuesta(texto=respuesta.texto, audio_base64=audio_base64)

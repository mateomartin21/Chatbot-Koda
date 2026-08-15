"""POST /api/mensajes — el endpoint central. runner_id sale SIEMPRE de get_current_runner(),
nunca del formulario. Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2."""

import base64
import logging
from datetime import UTC, datetime

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
from app.infrastructure.imagenes.sanitizar import ImagenInvalida, sanear
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos
from app.interfaces.api.deps import (
    Repos,
    get_coach_system_prompt,
    get_container,
    get_current_runner,
    get_llm_port,
    get_repos,
    get_scheduler,
    get_stt_port,
    get_tts_port,
    lanzar_extraccion_de_memoria,
)
from app.interfaces.avisos import enviar_aviso_ahora, programar_para

router = APIRouter(prefix="/api", tags=["mensajes"])
logger = logging.getLogger(__name__)


class MensajeRespuesta(BaseModel):
    texto: str
    audio_base64: str | None


class TurnoGuardado(BaseModel):
    rol: str
    contenido: str
    modalidad: str
    creado_en: datetime


# Cuantos mensajes se devuelven al abrir la aplicacion. No es el mismo numero que la
# ventana del modelo (10 turnos, contexto.py): esto es para que una persona reconozca
# de que estaba hablando, y para eso hace falta ver mas. Sigue siendo un tope: el
# runner que lleve un ano usando Koda no descarga su historial entero cada vez que
# abre la pestaña.
_MENSAJES_DEL_HISTORIAL = 40


@router.get("/conversacion", response_model=list[TurnoGuardado])
async def ver_conversacion(
    runner: Runner = Depends(get_current_runner),
    repos: Repos = Depends(get_repos),
) -> list[TurnoGuardado]:
    """Lo ultimo que os dijisteis, para pintarlo al abrir.

    El hilo ya se guardaba — es lo que alimenta la memoria del coach — pero solo lo
    leia el modelo. La persona volvia a abrir Koda y se encontraba una pantalla en
    blanco, como si no se conocieran de nada. Cerrar la pestaña no deberia ser lo
    mismo que empezar de cero.
    """
    mensajes = await repos.conversaciones.ultimos(runner.id, _MENSAJES_DEL_HISTORIAL)
    return [
        TurnoGuardado(
            rol=m.rol,
            contenido=m.contenido,
            modalidad=m.modalidad,
            creado_en=m.creado_en or datetime.now(UTC),
        )
        for m in mensajes
    ]


@router.post("/mensajes", response_model=MensajeRespuesta)
async def enviar_mensaje(
    runner: Runner = Depends(get_current_runner),
    texto: str | None = Form(None),
    audio: UploadFile | None = File(None),
    foto: UploadFile | None = File(None),
    stt: STTPort = Depends(get_stt_port),
    llm: LLMPort = Depends(get_llm_port),
    tts: TTSPort = Depends(get_tts_port),
    system_prompt: str = Depends(get_coach_system_prompt),
    repos: Repos = Depends(get_repos),
    container: Container = Depends(get_container),
    scheduler: APSchedulerAvisos = Depends(get_scheduler),
) -> MensajeRespuesta:
    audio_bytes = await audio.read() if audio is not None else None
    audio_mime = audio.content_type if audio is not None else None

    # La foto se sanea AQUI, en el borde: a partir de esta linea nadie maneja los
    # bytes que subio el navegador. Si no es una imagen, se contesta y se corta —
    # sin llamar al modelo, que es lo que cuesta dinero. Ver ADR-017.
    imagen = None
    if foto is not None:
        try:
            imagen = sanear(await foto.read())
        except ImagenInvalida:
            logger.info("Foto rechazada en el saneado")
            return MensajeRespuesta(
                texto="Esa foto no la puedo abrir. Prueba con otra, o dímelo hablando.",
                audio_base64=None,
            )

    repos_coach = ReposDelCoach(
        runners=repos.runners,
        planes=repos.planes,
        conversaciones=repos.conversaciones,
        memoria=repos.memoria,
        recordatorios=repos.recordatorios,
        reprogramar=lambda r: programar_para(r, repos.recordatorios, scheduler),
        enviar_aviso_ahora=lambda r, tipo: enviar_aviso_ahora(container, r, tipo),
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
        imagen=imagen,
    )

    # El turno se guarda DESPUES de responder: la memoria no puede estar en el camino
    # critico de la latencia. Si esto fallara, el runner ya tiene su respuesta.
    modalidad = "voz" if audio_bytes else "imagen" if imagen else "texto"
    turno = [
        Mensaje(rol="usuario", contenido=respuesta.texto_usuario, modalidad=modalidad),
        Mensaje(rol="coach", contenido=respuesta.texto, modalidad=modalidad),
    ]
    await repos.conversaciones.guardar(runner.id, turno)
    lanzar_extraccion_de_memoria(runner.id, turno, container)

    audio_base64 = base64.b64encode(respuesta.audio).decode() if respuesta.audio else None
    return MensajeRespuesta(texto=respuesta.texto, audio_base64=audio_base64)

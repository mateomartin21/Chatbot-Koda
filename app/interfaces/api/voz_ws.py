"""WS /ws/voz — nivel 0 del pipeline de voz (Nova Sonic, tiempo real). Mismo principio
que POST /api/mensajes: runner_id sale SIEMPRE de la cookie de sesion, nunca del cliente.
Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2 y
docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md.

Si Nova Sonic falla al abrir sesion o a media conversacion, el socket se cierra con
_CODIGO_CIERRE_FALLBACK — es la senal que el frontend usa para caer al flujo de siempre
(MediaRecorder + POST /api/mensajes, con su propio gateway de modelos por dentro)."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket

from app.application.coach import HERRAMIENTAS, ReposDelCoach, construir_system_prompt, ejecutor_para
from app.config import Settings
from app.domain.ports.voz_realtime_port import (
    ErrorSesion,
    FragmentoAudio,
    TranscripcionParcial,
    TurnoTerminado,
    VozRealtimePort,
)
from app.interfaces.api.deps import (
    COOKIE_NAME,
    Repos,
    get_coach_system_prompt,
    get_repos,
    get_settings,
    get_voz_realtime_port,
    runner_desde_token,
)

router = APIRouter(tags=["voz"])
logger = logging.getLogger(__name__)

_CODIGO_CIERRE_NO_AUTENTICADO = 4401
_CODIGO_CIERRE_FALLBACK = 4500


@router.websocket("/ws/voz")
async def voz_realtime(
    websocket: WebSocket,
    repos: Repos = Depends(get_repos),
    settings: Settings = Depends(get_settings),
    voz: VozRealtimePort = Depends(get_voz_realtime_port),
    system_prompt: str = Depends(get_coach_system_prompt),
) -> None:
    try:
        runner = await runner_desde_token(websocket.cookies.get(COOKIE_NAME), repos, settings)
    except Exception:  # noqa: BLE001 — HTTPException de auth, traducida a cierre de socket
        await websocket.close(code=_CODIGO_CIERRE_NO_AUTENTICADO)
        return

    await websocket.accept()

    try:
        # Mismas herramientas y mismo contexto que POST /api/mensajes: hablar y escribir
        # tienen que dar el mismo resultado, no dos Kodas distintos. El ejecutor queda
        # atado al runner de la cookie durante toda la sesion.
        sesion = await voz.abrir_sesion(
            system_prompt=construir_system_prompt(system_prompt, runner),
            herramientas=HERRAMIENTAS,
            ejecutar=ejecutor_para(runner, ReposDelCoach(runners=repos.runners, planes=repos.planes)),
        )
    except Exception:
        # Nova Sonic no disponible (ej. AccessDeniedException si el modelo no esta
        # habilitado en Bedrock -> Model access). El frontend cae a la cascada, pero esto
        # SI se loguea para poder diagnosticar la causa real.
        logger.warning("No se pudo abrir sesion de Nova Sonic", exc_info=True)
        await websocket.close(code=_CODIGO_CIERRE_FALLBACK)
        return

    async def recibir_del_navegador() -> None:
        # Bytes = audio crudo; texto = mensajes de control (hoy solo "fin_de_audio",
        # cuando el usuario suelta el boton de grabar). No cerramos el socket al
        # terminar de hablar -- eso mataria la sesion antes de que el modelo responda.
        # websocket.receive() (a diferencia de receive_bytes()) no lanza
        # WebSocketDisconnect solo -- hay que chequear el tipo a mano.
        while True:
            mensaje = await websocket.receive()
            if mensaje["type"] == "websocket.disconnect":
                return
            if mensaje.get("bytes") is not None:
                await sesion.enviar_audio(mensaje["bytes"])
            elif mensaje.get("text") is not None:
                control = json.loads(mensaje["text"])
                if control.get("tipo") == "fin_de_audio":
                    await sesion.terminar_turno_audio()
                elif control.get("tipo") == "mensaje_texto":
                    await sesion.enviar_texto(control["texto"])

    async def reenviar_al_navegador() -> None:
        async for evento in sesion.eventos():
            if isinstance(evento, TranscripcionParcial):
                await websocket.send_json(
                    {
                        "tipo": "transcripcion",
                        "texto": evento.texto,
                        "rol": evento.rol,
                        "definitiva": evento.definitiva,
                    }
                )
            elif isinstance(evento, FragmentoAudio):
                await websocket.send_bytes(evento.datos)
            elif isinstance(evento, TurnoTerminado):
                logger.info("Turno de Nova Sonic terminado (completionEnd)")
                await websocket.send_json({"tipo": "turno_terminado"})
            elif isinstance(evento, ErrorSesion):
                await websocket.close(code=_CODIGO_CIERRE_FALLBACK)
                return

    tarea_entrada = asyncio.create_task(recibir_del_navegador())
    tarea_salida = asyncio.create_task(reenviar_al_navegador())
    try:
        terminadas, _ = await asyncio.wait({tarea_entrada, tarea_salida}, return_when=asyncio.FIRST_COMPLETED)
        logger.info(
            "WS /ws/voz terminando: entrada_completa=%s salida_completa=%s",
            tarea_entrada in terminadas,
            tarea_salida in terminadas,
        )
    finally:
        tarea_entrada.cancel()
        tarea_salida.cancel()
        await sesion.cerrar()

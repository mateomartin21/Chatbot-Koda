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

from app.application.coach import HERRAMIENTAS, ejecutor_para
from app.application.contexto import ReposDelCoach, construir_contexto, construir_system_prompt
from app.config import Settings
from app.container import Container
from app.domain.models import Mensaje
from app.domain.ports.voz_realtime_port import (
    ErrorSesion,
    FragmentoAudio,
    TranscripcionParcial,
    TurnoTerminado,
    VozRealtimePort,
)
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos
from app.interfaces.api.deps import (
    COOKIE_NAME,
    Repos,
    get_coach_voz_prompt,
    get_container,
    get_repos,
    get_scheduler,
    get_settings,
    get_voz_realtime_port,
    lanzar_extraccion_de_memoria,
    runner_desde_token,
)
from app.interfaces.avisos import programar_para

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
    container: Container = Depends(get_container),
    scheduler: APSchedulerAvisos = Depends(get_scheduler),
    # Prompt propio, corto (ver container.build_container): con el de texto, Nova Sonic
    # ignoraba instrucciones que tenia escritas literalmente delante.
    system_prompt: str = Depends(get_coach_voz_prompt),
) -> None:
    try:
        runner = await runner_desde_token(websocket.cookies.get(COOKIE_NAME), repos, settings)
    except Exception:  # noqa: BLE001 — HTTPException de auth, traducida a cierre de socket
        await websocket.close(code=_CODIGO_CIERRE_NO_AUTENTICADO)
        return

    await websocket.accept()

    repos_coach = ReposDelCoach(
        runners=repos.runners,
        planes=repos.planes,
        conversaciones=repos.conversaciones,
        memoria=repos.memoria,
        recordatorios=repos.recordatorios,
        reprogramar=lambda r: programar_para(r, repos.recordatorios, scheduler),
    )
    try:
        # Mismas herramientas y mismo contexto que POST /api/mensajes: hablar y escribir
        # tienen que dar el mismo resultado, no dos Kodas distintos. El ejecutor queda
        # atado al runner de la cookie durante toda la sesion.
        #
        # El contexto se arma AQUI, al abrir: en Nova Sonic el system prompt se manda una
        # sola vez por sesion y no hay forma de ampliarlo despues. Como el navegador abre
        # una sesion nueva por cada mensaje, es tambien lo que hace que Koda recuerde lo
        # que se dijo hace un momento — sin esto, cada mensaje empezaba de cero.
        contexto = await construir_contexto(runner, repos_coach)
        sesion = await voz.abrir_sesion(
            system_prompt=construir_system_prompt(system_prompt, contexto),
            herramientas=HERRAMIENTAS,
            ejecutar=ejecutor_para(runner, repos_coach),
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
        # Se acumulan por separado la transcripcion confirmada y el adelanto de cada
        # lado. Guardar solo la confirmada perdia la mitad de los turnos: en voz,
        # Nova Sonic a menudo no manda nunca la FINAL, y la memoria acababa con lo que
        # dijo el runner y sin lo que le contesto Koda. Al cerrar el turno se guarda la
        # version mas completa de cada lado — el mismo criterio que ya usa la interfaz.
        definitivo: dict[str, list[str]] = {"usuario": [], "coach": []}
        adelanto: dict[str, list[str]] = {"usuario": [], "coach": []}

        async for evento in sesion.eventos():
            if isinstance(evento, TranscripcionParcial):
                destino = definitivo if evento.definitiva else adelanto
                destino.setdefault(evento.rol, []).append(evento.texto)
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
                await _guardar_turno(definitivo, adelanto)
                await websocket.send_json({"tipo": "turno_terminado"})
            elif isinstance(evento, ErrorSesion):
                await _guardar_turno(definitivo, adelanto)
                await websocket.close(code=_CODIGO_CIERRE_FALLBACK)
                return

    async def _guardar_turno(definitivo: dict[str, list[str]], adelanto: dict[str, list[str]]) -> None:
        mensajes = []
        for rol in ("usuario", "coach"):
            # La confirmada manda SIEMPRE que exista, aunque sea mas corta: el adelanto
            # es lo que el modelo penso decir y a veces no coincide con lo que dijo.
            # Solo cuando no llega ninguna se guarda el adelanto — es eso o perder el
            # turno entero, y un turno a medias vale mas que un hueco en la memoria.
            confirmada = " ".join(definitivo.get(rol, [])).strip()
            texto = confirmada or " ".join(adelanto.get(rol, [])).strip()
            if texto:
                mensajes.append(Mensaje(rol=rol, contenido=texto, modalidad="voz"))

        if mensajes:
            await repos.conversaciones.guardar(runner.id, mensajes)
            lanzar_extraccion_de_memoria(runner.id, mensajes, container)
        for acumulado in (definitivo, adelanto):
            for lista in acumulado.values():
                lista.clear()

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

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

from app.application.coach import HERRAMIENTAS_VOZ, NOMBRE_HERRAMIENTA_PUENTE, ejecutor_de_voz
from app.application.contexto import ReposDelCoach
from app.config import Settings
from app.container import Container
from app.domain.models import Mensaje
from app.domain.ports.llm_port import LlamadaHerramienta, LLMPort
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
    get_llm_port,
    get_repos,
    get_scheduler,
    get_settings,
    get_voz_locutor_prompt,
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
    # El cerebro. Es el mismo gateway de modelos que atiende /api/mensajes, con su
    # cascada de proveedores por dentro: hablar y escribir no son dos Kodas distintos.
    llm: LLMPort = Depends(get_llm_port),
    # Lo que oye Nova Sonic: como hablar y nada mas. Sin datos que poder equivocar.
    prompt_locutor: str = Depends(get_voz_locutor_prompt),
    # Lo que oye el cerebro cuando la consulta viene por voz: las mismas reglas de
    # siempre mas las de hablar, porque su respuesta se va a leer en alto.
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
        # Nova Sonic NO recibe el contexto del runner ni las cinco herramientas del
        # coach: recibe el prompt del locutor, que no contiene un solo dato, y UNA
        # herramienta que por dentro es una conversacion entera con el modelo grande.
        # Ver docs/adr/ADR-020-nova-habla-y-sonnet-decide.md.
        #
        # Que el prompt vaya vacio de datos no es una omision, es la garantia: un
        # modelo que no tiene el ritmo del runner en el contexto no puede decir un
        # ritmo equivocado. El contexto se arma dentro del puente, en cada consulta,
        # que ademas es mas fresco — antes se congelaba al abrir la sesion.
        #
        # Hablar y escribir siguen dando el mismo resultado porque detras hay el mismo
        # cerebro, las mismas herramientas y el mismo dominio.
        puente = ejecutor_de_voz(runner, repos_coach, llm=llm, system_prompt=system_prompt)
        # Si el locutor contesta sin consultar, lo que diga no esta fundado en nada.
        # Esto lo hace detectable; el rescate de mas abajo lo hace inofensivo.
        consultado = {"en_este_turno": False}

        async def consultar_al_entrenador(llamada: LlamadaHerramienta) -> str:
            consultado["en_este_turno"] = True
            return await puente(llamada)

        sesion = await voz.abrir_sesion(
            system_prompt=prompt_locutor,
            herramientas=HERRAMIENTAS_VOZ,
            ejecutar=consultar_al_entrenador,
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
                if not consultado["en_este_turno"]:
                    await _rescatar_turno_sin_consulta(definitivo, adelanto)
                consultado["en_este_turno"] = False
                await _guardar_turno(definitivo, adelanto)
                await websocket.send_json({"tipo": "turno_terminado"})
            elif isinstance(evento, ErrorSesion):
                await _guardar_turno(definitivo, adelanto)
                await websocket.close(code=_CODIGO_CIERRE_FALLBACK)
                return

    def _lo_que_dijo(acumulado: dict[str, list[str]], otro: dict[str, list[str]], rol: str) -> str:
        return (" ".join(acumulado.get(rol, [])) or " ".join(otro.get(rol, []))).strip()

    async def _rescatar_turno_sin_consulta(
        definitivo: dict[str, list[str]], adelanto: dict[str, list[str]]
    ) -> None:
        """El locutor cerro un turno sin preguntarle nada al entrenador.

        Su prompt no tiene un solo dato del runner, asi que no puede haber dicho un
        ritmo equivocado — como mucho una frase de relleno. Pero el runner pregunto
        algo y se ha quedado sin respuesta, y eso es igual de malo que una inventada:
        cree que le contestaron.

        Asi que se consulta desde aqui con lo que dijo, y la respuesta buena se manda
        al hilo. Va detras de lo que dijera el locutor, no en su lugar: al navegador
        ya le llego, y la unica forma de retirarlo seria que el audio no hubiera
        sonado — y ya sono.
        """
        dicho = _lo_que_dijo(definitivo, adelanto, "usuario")
        if not dicho:
            return  # nadie pregunto nada: no hay turno que rescatar

        logger.warning("La voz cerro un turno sin consultar al entrenador. Se rescata: %r", dicho)
        respuesta = await puente(
            LlamadaHerramienta(nombre=NOMBRE_HERRAMIENTA_PUENTE, argumentos={"peticion": dicho})
        )
        definitivo.setdefault("coach", []).append(respuesta)
        await websocket.send_json(
            {"tipo": "transcripcion", "texto": respuesta, "rol": "coach", "definitiva": True}
        )

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

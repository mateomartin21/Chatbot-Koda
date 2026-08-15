"""Ensamblado de los recordatorios: el job, el arranque y el enlace de baja.

Vive fuera de la API porque un aviso no nace de una petición HTTP, pero es el mismo
tipo de código que deps.py: junta un adaptador concreto con un caso de uso.
"""

import logging
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

import jwt

from app.application.contexto import ReposDelCoach
from app.application.recordatorios import DIA_DEL_SEMANAL, HORAS_POR_DEFECTO, enviar_recordatorio
from app.config import Settings
from app.container import Container
from app.domain.models import Recordatorio, Runner, TipoRecordatorio
from app.domain.ports.repositories import RecordatorioRepo
from app.domain.ports.scheduler_port import SchedulerPort
from app.infrastructure.persistence.repos import (
    SqlConversacionRepo,
    SqlMemoriaRepo,
    SqlPlanRepo,
    SqlRecordatorioRepo,
    SqlRunnerRepo,
)
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos

logger = logging.getLogger(__name__)

_USO_BAJA = "baja_recordatorios"
_ZONA_POR_DEFECTO = "America/Mexico_City"


# --- Enlace de baja -------------------------------------------------------------
#
# Va firmado y no lleva el email en claro: con una URL adivinable, cualquiera podria
# dar de baja a otro con solo probar identificadores. El token dura un anio porque un
# correo viejo tiene que seguir permitiendo darse de baja — es lo minimo exigible.


def crear_token_baja(runner_id: UUID, settings: Settings) -> str:
    ahora = datetime.now(UTC)
    payload = {"sub": str(runner_id), "uso": _USO_BAJA, "iat": ahora, "exp": ahora + timedelta(days=365)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def runner_de_token_baja(token: str, settings: Settings) -> UUID:
    """Lanza jwt.PyJWTError si el token no vale. El 'uso' se comprueba a mano: sin eso,
    una cookie de sesion robada serviria de enlace de baja y al reves."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("uso") != _USO_BAJA:
        raise jwt.InvalidTokenError("El token no es de baja de recordatorios")
    return UUID(payload["sub"])


def url_de_baja(runner_id: UUID, settings: Settings) -> str:
    return f"{settings.app_base_url}/api/recordatorios/baja?token={crear_token_baja(runner_id, settings)}"


# --- El job ---------------------------------------------------------------------


def crear_ejecutor(container: Container):
    """Devuelve la funcion que APScheduler llamara. Recibe solo strings porque es lo
    unico que viaja en un job: el identificador del runner y el tipo de aviso."""

    async def ejecutar(runner_id_texto: str, tipo_texto: str) -> None:
        runner_id, tipo = UUID(runner_id_texto), TipoRecordatorio(tipo_texto)
        try:
            async with container.session_factory() as session:
                enviado = await enviar_recordatorio(
                    runner_id=runner_id,
                    tipo=tipo,
                    repos=ReposDelCoach(
                        runners=SqlRunnerRepo(session),
                        planes=SqlPlanRepo(session),
                        conversaciones=SqlConversacionRepo(session),
                        memoria=SqlMemoriaRepo(session),
                    ),
                    recordatorios=SqlRecordatorioRepo(session),
                    email=container.email,
                    plantilla_html=container.plantilla_recordatorio,
                    url_baja=url_de_baja(runner_id, container.settings),
                    url_app=container.settings.app_base_url,
                )
            logger.info(
                "Aviso %s para %s: %s", tipo.value, runner_id, "enviado" if enviado else "sin nada que decir"
            )
        except Exception:  # noqa: BLE001 — un aviso fallido no puede tumbar el scheduler
            logger.warning("Fallo el aviso %s de %s", tipo.value, runner_id, exc_info=True)

    return ejecutar


async def enviar_aviso_ahora(container: Container, runner: Runner, tipo_texto: str) -> bool:
    """Manda un aviso fuera de su hora, para poder verlo.

    Un recordatorio que llega a las seis de la mañana no se le puede enseñar a nadie:
    ni al runner que quiere saber como es antes de fiarse, ni a quien evalua esto y no
    va a esperar a mañana. Sin esto, la funcion existe y no se puede demostrar.

    Usa el MISMO camino que el job del scheduler, no una copia: si el correo de prueba
    se redactara aparte, seria posible que el de prueba saliera bien y el de verdad
    no — que es el peor resultado de los tres.
    """
    async with container.session_factory() as session:
        enviado = await enviar_recordatorio(
            runner_id=runner.id,
            tipo=TipoRecordatorio(tipo_texto),
            repos=ReposDelCoach(
                runners=SqlRunnerRepo(session),
                planes=SqlPlanRepo(session),
                conversaciones=SqlConversacionRepo(session),
                memoria=SqlMemoriaRepo(session),
            ),
            recordatorios=SqlRecordatorioRepo(session),
            email=container.email,
            plantilla_html=container.plantilla_recordatorio,
            url_baja=url_de_baja(runner.id, container.settings),
            url_app=container.settings.app_base_url,
        )
    logger.info("Aviso %s mandado a mano para %s: %s", tipo_texto, runner.id, enviado)
    return enviado


# --- Arranque -------------------------------------------------------------------


async def reprogramar_todo(container: Container, scheduler: APSchedulerAvisos) -> int:
    """Reconstruye los avisos al arrancar desde la tabla, que es su unica fuente de
    verdad — ver docs/adr/ADR-014-jobs-en-memoria.md. Abre su propia sesion porque no
    nace de ninguna peticion."""
    async with container.session_factory() as session:
        recordatorios = await SqlRecordatorioRepo(session).activos_de_todos()
        runners = SqlRunnerRepo(session)
        programados = 0
        for recordatorio in recordatorios:
            runner = await runners.obtener(recordatorio.runner_id)
            if runner is None or not runner.activo:
                continue
            programar_uno(runner, recordatorio, scheduler)
            programados += 1
    logger.info("Avisos reprogramados al arrancar: %d", programados)
    return programados


def programar_uno(runner: Runner, recordatorio: Recordatorio, scheduler: SchedulerPort) -> None:
    """Un aviso, con la zona horaria del runner. Sin E/S: quien llama ya tiene los datos.

    Antes esto abria su propia sesion de base de datos, y por eso se saltaba los dobles
    de los tests y acababa escribiendo en Postgres de verdad. Recibir lo que necesita en
    vez de ir a buscarlo lo hace testeable y quita una sesion escondida.
    """
    if not recordatorio.activo:
        scheduler.cancelar(runner.id, recordatorio.tipo)
        return
    scheduler.programar(
        runner_id=runner.id,
        tipo=recordatorio.tipo,
        hora_local=recordatorio.hora_local,
        zona_horaria=runner.zona_horaria or _ZONA_POR_DEFECTO,
        dia_de_la_semana=DIA_DEL_SEMANAL if recordatorio.tipo is TipoRecordatorio.SEMANAL else None,
    )


async def programar_para(runner: Runner, recordatorios: RecordatorioRepo, scheduler: SchedulerPort) -> None:
    """Reprograma todos los avisos de UN runner con lo que diga el repositorio."""
    for recordatorio in await recordatorios.de_runner(runner.id):
        programar_uno(runner, recordatorio, scheduler)


async def alta_por_defecto(runner_id: UUID, recordatorios: RecordatorioRepo) -> None:
    """Un runner nuevo entra con los tres avisos a las horas por defecto. Es opt-out y
    no opt-in porque un recordatorio que hay que activar a mano no lo activa casi nadie.

    Si ya tiene recordatorios no se le toca ninguno, aunque esten dados de baja: darse
    de baja tiene que ser definitivo, no algo que se deshaga al volver a entrar.
    """
    if await recordatorios.de_runner(runner_id):
        return
    for tipo, hora in HORAS_POR_DEFECTO.items():
        await recordatorios.guardar(runner_id, tipo, time(hour=hora), activo=True)

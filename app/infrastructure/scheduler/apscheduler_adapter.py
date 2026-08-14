"""Adaptador de SchedulerPort sobre APScheduler.

Un job por runner y tipo de aviso, y **el job solo lleva un runner_id como argumento**.
Nunca un job que barra la tabla de sesiones del día y reparta correos por su cuenta:
eso es un cruce de destinatarios esperando a ocurrir
(docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.5).

El id del job es determinista — "diario:<uuid>" — para que reprogramar sea reemplazar
y no acumular: si el runner cambia la hora tres veces, sigue habiendo un solo aviso.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import time
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.domain.models import TipoRecordatorio
from app.domain.ports.scheduler_port import SchedulerPort

logger = logging.getLogger(__name__)

EjecutorDeAviso = Callable[[str, str], Awaitable[None]]


def _id_de_job(runner_id: UUID, tipo: TipoRecordatorio) -> str:
    return f"{tipo.value}:{runner_id}"


class APSchedulerAvisos(SchedulerPort):
    """Los jobs viven en memoria y se reconstruyen al arrancar desde la tabla
    `recordatorios` — ver docs/adr/ADR-014-jobs-en-memoria.md.

    El plan de ejecucion pedia un jobstore en Postgres. Se descarto porque entonces el
    mismo horario viviria en dos sitios (nuestra tabla y la de APScheduler) y podrian
    divergir: alguien cambia su hora, falla uno de los dos escritos, y el correo sigue
    llegando cuando no toca. Con la tabla como unica fuente de verdad eso no puede pasar.
    """

    def __init__(self, ejecutar: EjecutorDeAviso) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._ejecutar = ejecutar

    def iniciar(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def detener(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def programar(
        self,
        runner_id: UUID,
        tipo: TipoRecordatorio,
        hora_local: time,
        zona_horaria: str,
        dia_de_la_semana: int | None = None,
    ) -> None:
        disparador = CronTrigger(
            hour=hora_local.hour,
            minute=hora_local.minute,
            day_of_week=dia_de_la_semana,
            # La zona del RUNNER, no la del servidor: un aviso de las seis de la mañana
            # que llega a las tres es peor que no mandarlo. APScheduler recalcula el
            # proximo disparo en esta zona, asi que el horario de verano se ajusta solo.
            timezone=zona_horaria,
        )
        self._scheduler.add_job(
            self._ejecutar,
            trigger=disparador,
            # Lo UNICO que viaja al job es el identificador. Los datos del runner se
            # vuelven a cargar acotados por el cuando toca enviar.
            args=[str(runner_id), tipo.value],
            id=_id_de_job(runner_id, tipo),
            replace_existing=True,
            misfire_grace_time=3600,  # si el servidor estuvo caido, vale con mandarlo tarde
            coalesce=True,  # tras una caida larga, un solo correo y no cinco atrasados
        )
        logger.info(
            "Aviso %s programado para %s a las %s (%s)", tipo.value, runner_id, hora_local, zona_horaria
        )

    def cancelar(self, runner_id: UUID, tipo: TipoRecordatorio) -> None:
        """Deja el aviso sin programar. Que no estuviera programado no es un error:
        darse de baja dos veces tiene que ser inofensivo."""
        job = self._scheduler.get_job(_id_de_job(runner_id, tipo))
        if job is not None:
            job.remove()

    def cancelar_todos(self, runner_id: UUID) -> None:
        for tipo in TipoRecordatorio:
            self.cancelar(runner_id, tipo)

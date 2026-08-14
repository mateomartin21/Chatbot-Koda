"""Puerto de programación de avisos. Cero imports externos.

El dominio no sabe qué es APScheduler ni qué es un cron: sabe que hay algo que puede
llamarle "todos los días a las 6, en la zona horaria de este runner". Cambiar a
EventBridge + Lambda el día que haga falta es escribir otro adaptador.
"""

from abc import ABC, abstractmethod
from datetime import time
from uuid import UUID

from app.domain.models import TipoRecordatorio


class SchedulerPort(ABC):
    @abstractmethod
    def programar(
        self,
        runner_id: UUID,
        tipo: TipoRecordatorio,
        hora_local: time,
        zona_horaria: str,
        dia_de_la_semana: int | None = None,
    ) -> None:
        """Programa (o reprograma) un aviso. La hora es la del RUNNER.

        dia_de_la_semana solo para el resumen semanal; None = todos los días.
        """
        ...

    @abstractmethod
    def cancelar(self, runner_id: UUID, tipo: TipoRecordatorio) -> None: ...

    @abstractmethod
    def cancelar_todos(self, runner_id: UUID) -> None: ...

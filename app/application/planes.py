"""Casos de uso del plan de entrenamiento.

Esta capa no decide NADA de entrenamiento: no sabe cuantos kilometros toca ni cuando
hay descarga. Solo orquesta — coge los datos del runner, se los pasa al dominio y
guarda lo que salga. Todo el criterio deportivo vive en app/domain/training/ y esa
frontera es el argumento entero de docs/adr/ADR-006-dominio-determinista.md.

PlanNoViable (R6) se deja subir tal cual: que el sistema se niegue a preparar un
maraton en seis semanas no es un fallo que haya que capturar aqui, es la respuesta.
Cada interfaz la traduce a su formato — HTTP a un 409, el coach a una frase.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.domain.models import DatosPerfil, Runner
from app.domain.ports.repositories import PlanRepo, RunnerRepo
from app.domain.training.factory import estrategia_para
from app.domain.training.modelos import (
    Distancia,
    Objetivo,
    PlanActivo,
    SesionProgramada,
    fecha_inicio_para,
)


@dataclass(frozen=True)
class DatosDelPlan:
    """Lo minimo que hace falta para generar un plan. Lo demas sale del perfil."""

    distancia_km: float
    fecha_carrera: date
    dias_por_semana: int | None = None
    nombre_carrera: str | None = None
    tiempo_meta_seg: float | None = None


async def crear_plan(
    *,
    runner: Runner,
    datos: DatosDelPlan,
    runners: RunnerRepo,
    planes: PlanRepo,
    hoy: date | None = None,
) -> PlanActivo:
    """Genera el plan y lo guarda. Puede lanzar PlanNoViable (R6) o ValorInvalido."""
    hoy = hoy or date.today()
    distancia = Distancia.desde_km(datos.distancia_km)

    # Los dias por semana son parte del perfil, no del plan: si el runner los dice al
    # pedir un plan, se quedan guardados para la proxima vez y para los recordatorios.
    if datos.dias_por_semana is not None and datos.dias_por_semana != runner.dias_disponibles:
        runner = await runners.actualizar_perfil(
            runner.id, DatosPerfil(dias_disponibles=datos.dias_por_semana)
        )

    objetivo = Objetivo(
        distancia=distancia,
        fecha_carrera=datos.fecha_carrera,
        nombre_carrera=datos.nombre_carrera,
        tiempo_meta_seg=datos.tiempo_meta_seg,
    )
    plan = estrategia_para(distancia).generar(runner, objetivo, hoy=hoy)
    fecha_inicio = fecha_inicio_para(objetivo, len(plan.semanas), hoy)
    return await planes.guardar(runner.id, objetivo, plan, fecha_inicio)


async def consultar_plan_activo(runner_id: UUID, planes: PlanRepo) -> PlanActivo | None:
    return await planes.obtener_activo(runner_id)


async def consultar_proxima_sesion(
    runner_id: UUID, planes: PlanRepo, hoy: date | None = None
) -> SesionProgramada | None:
    return await planes.proxima_sesion(runner_id, hoy or date.today())


async def actualizar_perfil(runner: Runner, datos: DatosPerfil, runners: RunnerRepo) -> Runner:
    return await runners.actualizar_perfil(runner.id, datos)

"""El plan, desde que se pide hasta que se guarda.

El dominio ya esta probado en test_dominio_training.py: aqui no se vuelve a comprobar
ninguna regla de entrenamiento, solo que la orquestacion no pierda nada por el camino.
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.planes import (
    DatosDelPlan,
    consultar_plan_activo,
    consultar_proxima_sesion,
    crear_plan,
)
from app.domain.models import Runner
from app.domain.training.modelos import Distancia, PlanNoViable, TipoSesion, ValorInvalido
from tests.fakes.repos import InMemoryPlanRepo, InMemoryRunnerRepo

HOY = date(2026, 8, 13)  # un jueves


@pytest.fixture
def runners() -> InMemoryRunnerRepo:
    repo = InMemoryRunnerRepo()
    repo.agregar(
        Runner(
            id=uuid4(),
            email="corredor@example.com",
            creado_en=datetime(2026, 1, 1),
            nivel="intermedio",
            dias_disponibles=4,
            marca_distancia_km=5,
            marca_tiempo_seg=25 * 60,
        )
    )
    return repo


@pytest.fixture
def planes() -> InMemoryPlanRepo:
    return InMemoryPlanRepo()


@pytest.fixture
def runner(runners: InMemoryRunnerRepo) -> Runner:
    return next(iter(runners._runners.values()))


def _datos(semanas: int = 13, distancia_km: float = 10, **extra) -> DatosDelPlan:
    return DatosDelPlan(distancia_km=distancia_km, fecha_carrera=HOY + timedelta(weeks=semanas), **extra)


async def test_el_plan_creado_es_el_que_se_lee_despues(runner, runners, planes):
    creado = await crear_plan(runner=runner, datos=_datos(), runners=runners, planes=planes, hoy=HOY)
    leido = await consultar_plan_activo(runner.id, planes)

    assert leido is not None
    assert leido.id == creado.id
    assert leido.objetivo.distancia == Distancia.K10


async def test_el_plan_termina_la_semana_de_la_carrera(runner, runners, planes):
    """El taper solo sirve si acaba el dia de la carrera: por eso el plan se ancla al
    final y no al principio."""
    datos = _datos(semanas=13)
    plan = await crear_plan(runner=runner, datos=datos, runners=runners, planes=planes, hoy=HOY)

    ultima = max(s.fecha for s in plan.sesiones_programadas())
    lunes_de_la_carrera = datos.fecha_carrera - timedelta(days=datos.fecha_carrera.weekday())
    assert lunes_de_la_carrera <= ultima <= datos.fecha_carrera


async def test_pedir_el_plan_con_otra_frecuencia_actualiza_el_perfil(runner, runners, planes):
    """Los dias por semana son del runner, no del plan: se quedan para la proxima vez."""
    await crear_plan(runner=runner, datos=_datos(dias_por_semana=6), runners=runners, planes=planes, hoy=HOY)
    assert (await runners.obtener(runner.id)).dias_disponibles == 6


async def test_un_objetivo_imposible_no_se_guarda(runner, runners, planes):
    with pytest.raises(PlanNoViable):
        await crear_plan(
            runner=runner,
            datos=_datos(semanas=6, distancia_km=42),
            runners=runners,
            planes=planes,
            hoy=HOY,
        )
    assert await consultar_plan_activo(runner.id, planes) is None


async def test_una_distancia_que_no_existe_se_rechaza(runner, runners, planes):
    with pytest.raises(ValorInvalido):
        await crear_plan(runner=runner, datos=_datos(distancia_km=7), runners=runners, planes=planes, hoy=HOY)


async def test_la_proxima_sesion_nunca_es_un_descanso(runner, runners, planes):
    plan = await crear_plan(runner=runner, datos=_datos(), runners=runners, planes=planes, hoy=HOY)
    proxima = await consultar_proxima_sesion(runner.id, planes, hoy=plan.fecha_inicio)

    assert proxima is not None
    assert proxima.sesion.tipo is not TipoSesion.DESCANSO
    assert proxima.fecha >= plan.fecha_inicio


async def test_un_plan_nuevo_jubila_al_anterior(runner, runners, planes):
    await crear_plan(runner=runner, datos=_datos(), runners=runners, planes=planes, hoy=HOY)
    segundo = await crear_plan(
        runner=runner, datos=_datos(semanas=17, distancia_km=21), runners=runners, planes=planes, hoy=HOY
    )

    activo = await consultar_plan_activo(runner.id, planes)
    assert activo is not None
    assert activo.id == segundo.id
    assert activo.objetivo.distancia == Distancia.K21

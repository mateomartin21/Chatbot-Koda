"""Las herramientas que el LLM puede pedir.

Lo que se prueba no es que devuelvan texto bonito, sino que el modelo no pueda usarlas
para hacer algo que el dominio prohibe ni para tocar los datos de otro.
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.coach import HERRAMIENTAS, ReposDelCoach, construir_system_prompt, ejecutor_para
from app.domain.models import Runner
from app.domain.ports.llm_port import LlamadaHerramienta
from tests.fakes.repos import InMemoryPlanRepo, InMemoryRunnerRepo

HOY = date(2026, 8, 13)


def _runner(**campos) -> Runner:
    return Runner(id=uuid4(), email="corredor@example.com", creado_en=datetime(2026, 1, 1), **campos)


@pytest.fixture
def repos() -> ReposDelCoach:
    return ReposDelCoach(runners=InMemoryRunnerRepo(), planes=InMemoryPlanRepo())


@pytest.fixture
def runner(repos: ReposDelCoach) -> Runner:
    r = _runner(nivel="intermedio", dias_disponibles=4, marca_distancia_km=5, marca_tiempo_seg=1500)
    repos.runners.agregar(r)
    return r


def _llamar(_nombre: str, **argumentos) -> LlamadaHerramienta:
    # El nombre del parametro lleva guion bajo porque "nombre" es tambien un argumento
    # valido de guardar_datos_del_runner.
    return LlamadaHerramienta(nombre=_nombre, argumentos=argumentos)


async def test_crear_plan_guarda_el_plan_y_lo_describe(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    resultado = await ejecutar(
        _llamar("crear_plan", distancia_km=10, fecha_carrera=str(HOY + timedelta(weeks=13)))
    )

    assert "10K" in resultado
    assert await repos.planes.obtener_activo(runner.id) is not None


async def test_un_objetivo_imposible_vuelve_como_rechazo_con_alternativa(runner, repos):
    """R6 llega al modelo como texto que le obliga a ofrecer algo, no como un error."""
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    resultado = await ejecutar(
        _llamar("crear_plan", distancia_km=42, fecha_carrera=str(HOY + timedelta(weeks=6)))
    )

    assert "RECHAZADO" in resultado
    assert "21K" in resultado
    assert await repos.planes.obtener_activo(runner.id) is None


async def test_una_fecha_mal_escrita_no_revienta_la_conversacion(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    resultado = await ejecutar(_llamar("crear_plan", distancia_km=10, fecha_carrera="en noviembre"))
    assert "AAAA-MM-DD" in resultado


async def test_lo_que_se_guarda_del_perfil_se_usa_en_el_plan_del_mismo_turno(repos):
    """El turno tipico son dos llamadas: guardar lo que acaban de contar y crear el
    plan. Si la segunda usara el perfil de antes, los ritmos saldrian mal."""
    runner = _runner()
    repos.runners.agregar(runner)
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    await ejecutar(
        _llamar("guardar_datos_del_runner", nivel="avanzado", marca_distancia_km=10, marca_tiempo_seg=2400)
    )
    await ejecutar(_llamar("crear_plan", distancia_km=21, fecha_carrera=str(HOY + timedelta(weeks=16))))

    activo = await repos.planes.obtener_activo(runner.id)
    assert activo is not None
    assert not activo.plan.ritmos_estimados  # la marca guardada llego al calculo


async def test_ninguna_herramienta_acepta_runner_id(runner, repos):
    """Si el modelo pudiera elegir el runner_id, bastaria un prompt para leer los datos
    de otro. Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2."""
    for herramienta in HERRAMIENTAS:
        assert "runner_id" not in herramienta.esquema.get("properties", {})


async def test_un_runner_id_colado_en_los_argumentos_se_ignora(repos):
    victima = _runner(nombre="Victima")
    atacante = _runner()
    repos.runners.agregar(victima)
    repos.runners.agregar(atacante)
    ejecutar = ejecutor_para(atacante, repos, hoy=HOY)

    await ejecutar(_llamar("guardar_datos_del_runner", nombre="Atacante", runner_id=str(victima.id)))

    assert (await repos.runners.obtener(victima.id)).nombre == "Victima"
    assert (await repos.runners.obtener(atacante.id)).nombre == "Atacante"


async def test_una_herramienta_inventada_no_rompe_nada(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    assert "No existe" in await ejecutar(_llamar("borrar_todo"))


async def test_el_prompt_lleva_la_fecha_y_lo_que_se_sabe_del_runner(runner):
    prompt = construir_system_prompt("eres koda", runner, hoy=HOY)

    assert "13 de agosto de 2026" in prompt
    assert "intermedio" in prompt


async def test_el_prompt_dice_cuando_no_se_sabe_nada_del_runner():
    prompt = construir_system_prompt("eres koda", _runner(), hoy=HOY)
    assert "Todavia no sabes nada" in prompt

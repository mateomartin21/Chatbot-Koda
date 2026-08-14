"""El ensamblado del contexto: las tres capas de docs/contexto/05-MEMORIA.md.

El test que de verdad importa aqui es el ultimo: que los hechos de un runner no se
cuelen en el prompt de otro. construir_contexto es la frontera de aislamiento (§4.3),
asi que es el sitio donde se audita esa sospecha.
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.contexto import ReposDelCoach, construir_contexto, construir_system_prompt
from app.application.planes import DatosDelPlan, crear_plan
from app.domain.models import Hecho, Mensaje, Runner
from tests.fakes.repos import (
    InMemoryConversacionRepo,
    InMemoryMemoriaRepo,
    InMemoryPlanRepo,
    InMemoryRunnerRepo,
)

HOY = date(2026, 8, 13)
BASE = "eres koda, el prompt largo de siempre"


def _runner(**campos) -> Runner:
    return Runner(id=uuid4(), email=f"{uuid4().hex}@example.com", creado_en=datetime(2026, 1, 1), **campos)


@pytest.fixture
def repos() -> ReposDelCoach:
    return ReposDelCoach(
        runners=InMemoryRunnerRepo(),
        planes=InMemoryPlanRepo(),
        conversaciones=InMemoryConversacionRepo(),
        memoria=InMemoryMemoriaRepo(),
    )


@pytest.fixture
def runner(repos: ReposDelCoach) -> Runner:
    r = _runner(nivel="intermedio", dias_disponibles=4, marca_distancia_km=5, marca_tiempo_seg=1500)
    repos.runners.agregar(r)
    return r


async def _prompt_de(runner: Runner, repos: ReposDelCoach) -> str:
    return construir_system_prompt(BASE, await construir_contexto(runner, repos, hoy=HOY))


async def test_el_contexto_lleva_la_fecha_y_el_perfil(runner, repos):
    prompt = await _prompt_de(runner, repos)

    assert "13 de agosto de 2026" in prompt
    assert "intermedio" in prompt
    # El contexto va DELANTE del prompt largo: al final, Nova Sonic lo ignoraba.
    assert prompt.index("13 de agosto") < prompt.index(BASE)


async def test_sin_datos_el_prompt_lo_dice_en_vez_de_callarselo(repos):
    prompt = await _prompt_de(_runner(), repos)
    assert "No sabes nada de este runner" in prompt


async def test_una_marca_sin_tiempo_se_senala_como_incompleta(repos):
    prompt = await _prompt_de(_runner(marca_distancia_km=10), repos)
    assert "NO en cuanto tiempo" in prompt


async def test_el_plan_activo_entra_en_el_contexto(runner, repos):
    await crear_plan(
        runner=runner,
        datos=DatosDelPlan(distancia_km=10, fecha_carrera=HOY + timedelta(weeks=13)),
        runners=repos.runners,
        planes=repos.planes,
        hoy=HOY,
    )
    prompt = await _prompt_de(runner, repos)

    assert "Plan de 10K" in prompt
    assert "Siguiente sesion" in prompt


async def test_sin_plan_el_prompt_tambien_lo_dice(runner, repos):
    assert "No tiene ningun plan activo" in await _prompt_de(runner, repos)


async def test_los_ultimos_turnos_van_en_el_prompt(runner, repos):
    """Capa 2. Sin esto, cada mensaje abria una sesion en blanco: el runner decia
    'maraton' y en el mensaje siguiente Koda le preguntaba la distancia."""
    await repos.conversaciones.guardar(
        runner.id,
        [
            Mensaje(rol="usuario", contenido="quiero correr un maraton"),
            Mensaje(rol="coach", contenido="¿que fecha tienes en mente?"),
        ],
    )
    prompt = await _prompt_de(runner, repos)

    assert "quiero correr un maraton" in prompt
    assert "NO saludes de nuevo" in prompt


async def test_la_ventana_corta_no_crece_sin_limite(runner, repos):
    """El coste por mensaje tiene que ser constante aunque lleve un anio usando la app."""
    await repos.conversaciones.guardar(
        runner.id, [Mensaje(rol="usuario", contenido=f"mensaje {i}") for i in range(40)]
    )
    contexto = await construir_contexto(runner, repos, hoy=HOY)

    assert len(contexto.recientes) == 10
    assert contexto.recientes[-1].contenido == "mensaje 39"  # los ultimos, no los primeros


async def test_los_hechos_recordados_van_en_el_prompt(runner, repos):
    await repos.memoria.guardar(
        runner.id, [Hecho(categoria="lesion", hecho="molestia en la rodilla al bajar cuestas")]
    )
    prompt = await _prompt_de(runner, repos)

    assert "molestia en la rodilla" in prompt
    assert "(lesion)" in prompt


async def test_un_hecho_repetido_no_se_guarda_dos_veces(runner, repos):
    """§4.2: una memoria que solo acumula se pudre."""
    await repos.memoria.guardar(runner.id, [Hecho(categoria="preferencia", hecho="Corre por la mañana")])
    guardados = await repos.memoria.guardar(
        runner.id, [Hecho(categoria="preferencia", hecho="corre por la manana.")]
    )

    assert guardados == 0
    assert len(await repos.memoria.vigentes(runner.id)) == 1


async def test_el_contexto_de_a_no_contiene_nada_de_b(repos):
    """La frontera de aislamiento de 03-MULTIUSUARIO §4.3, comprobada donde vive."""
    ana, bruno = _runner(nombre="Ana"), _runner(nombre="Bruno")
    repos.runners.agregar(ana)
    repos.runners.agregar(bruno)

    await repos.memoria.guardar(bruno.id, [Hecho(categoria="lesion", hecho="fractura de peroné")])
    await repos.conversaciones.guardar(
        bruno.id, [Mensaje(rol="usuario", contenido="me opero la semana que viene")]
    )
    await crear_plan(
        runner=bruno,
        datos=DatosDelPlan(distancia_km=42, fecha_carrera=HOY + timedelta(weeks=20)),
        runners=repos.runners,
        planes=repos.planes,
        hoy=HOY,
    )

    prompt_de_ana = await _prompt_de(ana, repos)

    assert "peroné" not in prompt_de_ana
    assert "me opero" not in prompt_de_ana
    assert "42K" not in prompt_de_ana
    assert "Bruno" not in prompt_de_ana


async def test_un_plan_que_aun_no_ha_empezado_lo_avisa(runner, repos):
    """El plan se cuenta hacia atras desde la carrera, asi que suele arrancar unos dias
    despues de pedirlo. Sin avisarlo, parece un error de fechas — y lo parecio."""
    await crear_plan(
        runner=runner,
        datos=DatosDelPlan(distancia_km=42, fecha_carrera=HOY + timedelta(weeks=18)),
        runners=repos.runners,
        planes=repos.planes,
        hoy=HOY,
    )
    activo = await repos.planes.obtener_activo(runner.id)

    assert activo.fecha_inicio > HOY  # el plan no arranca hoy
    assert "todavia no ha empezado" in await _prompt_de(runner, repos)


async def test_un_plan_ya_en_marcha_no_avisa_de_nada(runner, repos):
    """El mismo plan, consultado cuando ya arranco: el aviso desaparece solo."""
    await crear_plan(
        runner=runner,
        datos=DatosDelPlan(distancia_km=10, fecha_carrera=HOY + timedelta(weeks=13)),
        runners=repos.runners,
        planes=repos.planes,
        hoy=HOY,
    )
    activo = await repos.planes.obtener_activo(runner.id)
    ya_empezado = construir_system_prompt(
        BASE, await construir_contexto(runner, repos, hoy=activo.fecha_inicio)
    )

    assert "todavia no ha empezado" not in ya_empezado

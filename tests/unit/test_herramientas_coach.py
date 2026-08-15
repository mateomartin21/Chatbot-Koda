"""Las herramientas que el LLM puede pedir.

Lo que se prueba no es que devuelvan texto bonito, sino que el modelo no pueda usarlas
para hacer algo que el dominio prohibe ni para tocar los datos de otro.
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.coach import HERRAMIENTAS, ejecutor_para
from app.application.contexto import ReposDelCoach, fecha_hablada
from app.domain.models import Runner
from app.domain.ports.llm_port import LlamadaHerramienta
from tests.fakes.repos import (
    InMemoryConversacionRepo,
    InMemoryMemoriaRepo,
    InMemoryPlanRepo,
    InMemoryRecordatorioRepo,
    InMemoryRunnerRepo,
)

HOY = date(2026, 8, 13)


def _runner(**campos) -> Runner:
    return Runner(id=uuid4(), email="corredor@example.com", creado_en=datetime(2026, 1, 1), **campos)


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


def _llamar(_nombre: str, **argumentos) -> LlamadaHerramienta:
    # El nombre del parametro lleva guion bajo porque "nombre" es tambien un argumento
    # valido de guardar_datos_del_runner.
    return LlamadaHerramienta(nombre=_nombre, argumentos=argumentos)


async def test_crear_plan_guarda_el_plan_y_lo_describe(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    carrera = HOY + timedelta(weeks=13)
    resultado = await ejecutar(
        _llamar("crear_plan", distancia_km=10, dia=carrera.day, mes=carrera.month, anio=carrera.year)
    )

    assert "10K" in resultado
    assert await repos.planes.obtener_activo(runner.id) is not None


async def test_un_objetivo_imposible_vuelve_como_rechazo_con_alternativa(runner, repos):
    """R6 llega al modelo como texto que le obliga a ofrecer algo, no como un error."""
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    carrera = HOY + timedelta(weeks=6)
    resultado = await ejecutar(
        _llamar("crear_plan", distancia_km=42, dia=carrera.day, mes=carrera.month, anio=carrera.year)
    )

    assert "RECHAZADO" in resultado
    assert "21K" in resultado
    assert await repos.planes.obtener_activo(runner.id) is None


async def test_el_rechazo_le_devuelve_la_fecha_para_que_no_la_vuelva_a_preguntar(runner, repos):
    """Hablando pasaba esto: Koda proponia "un 21K" a secas, el runner aceptaba, y en
    el turno siguiente le preguntaba cuando quiere correr — una fecha que le acababan
    de decir dos frases antes.

    Entre turno y turno lo unico que sobrevive es lo que Koda dijo en voz alta, asi
    que el rechazo tiene que devolverle la fecha de tres formas: dicha, con la orden
    de repetirla, y ya troceada en los argumentos de la proxima llamada."""
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    carrera = HOY + timedelta(weeks=6)

    resultado = await ejecutar(
        _llamar("crear_plan", distancia_km=42, dia=carrera.day, mes=carrera.month, anio=carrera.year)
    )

    assert f"dia {carrera.day}" in resultado
    assert f"mes {carrera.month}" in resultado
    assert "NO le preguntes la fecha otra vez" in resultado
    # Y la fecha hablada, que es la que va a repetir en voz alta y por tanto la unica
    # que sobrevive al turno.
    assert fecha_hablada(carrera) in resultado


async def test_sin_dia_ni_mes_no_revienta_la_conversacion(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    resultado = await ejecutar(_llamar("crear_plan", distancia_km=10))
    assert "Falta el dia o el mes" in resultado


async def test_lo_que_se_guarda_del_perfil_se_usa_en_el_plan_del_mismo_turno(repos):
    """El turno tipico son dos llamadas: guardar lo que acaban de contar y crear el
    plan. Si la segunda usara el perfil de antes, los ritmos saldrian mal."""
    runner = _runner()
    repos.runners.agregar(runner)
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    await ejecutar(
        _llamar("guardar_datos_del_runner", nivel="avanzado", marca_distancia_km=10, marca_tiempo_seg=2400)
    )
    carrera = HOY + timedelta(weeks=16)
    await ejecutar(
        _llamar("crear_plan", distancia_km=21, dia=carrera.day, mes=carrera.month, anio=carrera.year)
    )

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


async def test_sin_anio_la_carrera_es_la_proxima_vez_que_ocurra(runner, repos):
    """Nadie dice el anio en voz alta, y pedirlo cuesta un turno entero de conversacion."""
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)  # 13 de agosto de 2026

    await ejecutar(_llamar("crear_plan", distancia_km=10, dia=15, mes=11))

    activo = await repos.planes.obtener_activo(runner.id)
    assert activo is not None
    assert activo.objetivo.fecha_carrera == date(2026, 11, 15)


async def test_sin_anio_una_fecha_ya_pasada_salta_al_siguiente(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    await ejecutar(_llamar("crear_plan", distancia_km=10, dia=1, mes=3))

    activo = await repos.planes.obtener_activo(runner.id)
    assert activo is not None
    assert activo.objetivo.fecha_carrera == date(2027, 3, 1)


async def test_tambien_acepta_la_fecha_entera_si_el_modelo_improvisa(runner, repos):
    """El esquema pide dia y mes, pero los modelos improvisan: mandar la fecha ISO
    completa es la improvisacion mas probable y rechazarla costaria un turno de mas."""
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    await ejecutar(_llamar("crear_plan", distancia_km=10, fecha_carrera="2026-11-15"))

    activo = await repos.planes.obtener_activo(runner.id)
    assert activo is not None
    assert activo.objetivo.fecha_carrera == date(2026, 11, 15)


async def test_el_anio_explicito_manda_sobre_la_deduccion(runner, repos):
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    await ejecutar(_llamar("crear_plan", distancia_km=10, dia=15, mes=11, anio=2027))

    activo = await repos.planes.obtener_activo(runner.id)
    assert activo is not None
    assert activo.objetivo.fecha_carrera == date(2027, 11, 15)


async def test_mandar_ahora_entrega_el_aviso_fuera_de_su_hora(runner, repos):
    """Un recordatorio que llega a las seis de la mañana no se le puede enseñar a
    nadie. Sin esto, la funcion existe y no hay forma de demostrarla."""
    mandados = []

    async def fake_enviar(r, tipo):
        mandados.append((r.id, tipo))
        return True

    repos.recordatorios = InMemoryRecordatorioRepo()
    repos.enviar_aviso_ahora = fake_enviar
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    respuesta = await ejecutar(_llamar("configurar_recordatorio", tipo="diario", mandar_ahora=True))

    assert mandados == [(runner.id, "diario")]
    assert runner.email in respuesta


async def test_mandar_ahora_no_cambia_la_hora_configurada(runner, repos):
    """Es enseñarlo, no reconfigurarlo. Si de paso moviera la hora, el runner
    acabaria recibiendo el aviso diario a las once de la noche por haber pedido verlo."""

    async def fake_enviar(_r, _tipo):
        return True

    repos.recordatorios = InMemoryRecordatorioRepo()
    repos.enviar_aviso_ahora = fake_enviar
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    await ejecutar(_llamar("configurar_recordatorio", tipo="diario", hora=6))
    antes = await repos.recordatorios.de_runner(runner.id)
    await ejecutar(_llamar("configurar_recordatorio", tipo="diario", mandar_ahora=True, hora=23))
    despues = await repos.recordatorios.de_runner(runner.id)

    assert [(r.tipo, r.hora_local) for r in antes] == [(r.tipo, r.hora_local) for r in despues]


async def test_si_no_hay_nada_que_contar_lo_dice_en_vez_de_mandar_un_correo_vacio(runner, repos):
    async def fake_enviar(_r, _tipo):
        return False

    repos.recordatorios = InMemoryRecordatorioRepo()
    repos.enviar_aviso_ahora = fake_enviar
    ejecutar = ejecutor_para(runner, repos, hoy=HOY)

    respuesta = await ejecutar(_llamar("configurar_recordatorio", tipo="diario", mandar_ahora=True))

    assert "no habia nada que contar" in respuesta.lower()

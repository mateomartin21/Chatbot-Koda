"""Los tres correos.

La regla que se prueba una y otra vez aqui es la misma: **un correo que no dice nada no
se manda**. Un recordatorio que repite "hoy descansa" siete veces enseña al runner a
ignorarlos, y a partir de ahi da igual lo bueno que sea el correo del dia que importa.
"""

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest

from app.application.contexto import ReposDelCoach
from app.application.planes import DatosDelPlan, crear_plan
from app.application.recordatorios import (
    ContenidoCorreo,
    descrito,
    enviar_recordatorio,
    redactar_diario,
    renderizar_html,
)
from app.domain.models import Recordatorio, Runner, TipoRecordatorio
from tests.fakes.email import FakeEmail
from tests.fakes.repos import (
    InMemoryConversacionRepo,
    InMemoryMemoriaRepo,
    InMemoryPlanRepo,
    InMemoryRecordatorioRepo,
    InMemoryRunnerRepo,
)

HOY = date(2026, 8, 17)  # lunes
PLANTILLA = "<html>{{titulo}}|{{cuerpo}}|{{url_baja}}|{{url_app}}</html>"


def _runner(**campos) -> Runner:
    campos.setdefault("nivel", "intermedio")
    campos.setdefault("dias_disponibles", 4)
    campos.setdefault("marca_distancia_km", 5)
    campos.setdefault("marca_tiempo_seg", 1500)
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
def recordatorios() -> InMemoryRecordatorioRepo:
    return InMemoryRecordatorioRepo()


@pytest.fixture
def email() -> FakeEmail:
    return FakeEmail()


async def _con_plan(repos: ReposDelCoach, runner: Runner, semanas: int = 13, distancia: float = 10):
    repos.runners.agregar(runner)
    await crear_plan(
        runner=runner,
        datos=DatosDelPlan(distancia_km=distancia, fecha_carrera=HOY + timedelta(weeks=semanas)),
        runners=repos.runners,
        planes=repos.planes,
        hoy=HOY,
    )
    return await repos.planes.obtener_activo(runner.id)


async def _enviar(tipo, runner, repos, recordatorios, email, hoy):
    return await enviar_recordatorio(
        runner_id=runner.id,
        tipo=tipo,
        repos=repos,
        recordatorios=recordatorios,
        email=email,
        plantilla_html=PLANTILLA,
        url_baja="https://koda.test/baja?token=abc",
        url_app="https://koda.test",
        hoy=hoy,
    )


# --- Que se manda y que no ------------------------------------------------------


async def test_sin_plan_no_se_manda_nada(repos, recordatorios, email):
    runner = _runner()
    repos.runners.agregar(runner)

    assert await _enviar(TipoRecordatorio.DIARIO, runner, repos, recordatorios, email, HOY) is False
    assert email.enviados == []


async def test_un_dia_de_descanso_no_genera_correo(repos, recordatorios, email):
    """Lo mas facil de hacer mal: mandar 'hoy descansa' y quemar el canal."""
    runner = _runner(dias_disponibles=3)
    plan = await _con_plan(repos, runner)
    dias_con_sesion = {s.fecha for s in plan.sesiones_programadas()}
    descanso = next(
        plan.fecha_inicio + timedelta(days=d)
        for d in range(7)
        if plan.fecha_inicio + timedelta(days=d) not in dias_con_sesion
    )

    assert await _enviar(TipoRecordatorio.DIARIO, runner, repos, recordatorios, email, descanso) is False
    assert email.enviados == []


async def test_el_dia_de_una_sesion_si_llega_correo(repos, recordatorios, email):
    runner = _runner()
    plan = await _con_plan(repos, runner)
    dia = min(s.fecha for s in plan.sesiones_programadas())

    assert await _enviar(TipoRecordatorio.DIARIO, runner, repos, recordatorios, email, dia) is True

    correo = email.enviados[0]
    assert correo.destinatario == runner.email
    assert "km" in correo.texto
    # el enlace de baja va tambien en la version de texto plano, no solo en el HTML
    assert "baja" in correo.texto
    assert correo.html is not None


async def test_el_checkin_solo_llega_los_dias_que_habia_algo_que_hacer(repos, recordatorios, email):
    runner = _runner()
    plan = await _con_plan(repos, runner)
    con_sesion = min(s.fecha for s in plan.sesiones_programadas())
    dias_con_sesion = {s.fecha for s in plan.sesiones_programadas()}
    sin_sesion = next(
        plan.fecha_inicio + timedelta(days=d)
        for d in range(7)
        if plan.fecha_inicio + timedelta(days=d) not in dias_con_sesion
    )

    assert await _enviar(TipoRecordatorio.CHECKIN, runner, repos, recordatorios, email, con_sesion) is True
    assert await _enviar(TipoRecordatorio.CHECKIN, runner, repos, recordatorios, email, sin_sesion) is False


async def test_el_semanal_cuenta_los_kilometros_de_la_semana_que_entra(repos, recordatorios, email):
    runner = _runner()
    plan = await _con_plan(repos, runner)
    domingo_antes = plan.fecha_inicio - timedelta(days=1)

    assert await _enviar(TipoRecordatorio.SEMANAL, runner, repos, recordatorios, email, domingo_antes) is True

    correo = email.enviados[0]
    assert "semana 1" in correo.asunto.lower()
    assert "25.0 km" in correo.asunto  # el volumen va en el asunto: se ve sin abrir
    assert "la 1 de 12" in correo.texto  # y en que punto del plan esta


async def test_terminado_el_plan_dejan_de_llegar_correos(repos, recordatorios, email):
    """Un plan que acabo no debe seguir escribiendo: es la via rapida al boton de spam."""
    runner = _runner()
    plan = await _con_plan(repos, runner)
    despues = plan.objetivo.fecha_carrera + timedelta(days=30)

    for tipo in TipoRecordatorio:
        assert await _enviar(tipo, runner, repos, recordatorios, email, despues) is False


async def test_a_un_runner_dado_de_baja_de_la_app_no_se_le_escribe(repos, recordatorios, email):
    runner = _runner(activo=False)
    await _con_plan(repos, runner)
    plan = await repos.planes.obtener_activo(runner.id)
    dia = min(s.fecha for s in plan.sesiones_programadas())

    assert await _enviar(TipoRecordatorio.DIARIO, runner, repos, recordatorios, email, dia) is False


async def test_se_apunta_cuando_se_mando(repos, recordatorios, email):
    runner = _runner()
    plan = await _con_plan(repos, runner)
    dia = min(s.fecha for s in plan.sesiones_programadas())
    await recordatorios.guardar(runner.id, TipoRecordatorio.DIARIO, time(6, 0), activo=True)

    await _enviar(TipoRecordatorio.DIARIO, runner, repos, recordatorios, email, dia)

    guardado = (await recordatorios.de_runner(runner.id))[0]
    assert guardado.ultima_ejecucion is not None


# --- Aislamiento ----------------------------------------------------------------


async def test_el_correo_de_uno_no_lleva_nada_del_otro(repos, recordatorios, email):
    """El job solo conoce un runner_id; todo lo demas se recarga acotado por el.
    Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.5."""
    ana = _runner(nombre="Ana")
    bruno = _runner(nombre="Bruno")
    plan_de_ana = await _con_plan(repos, ana, semanas=13, distancia=10)
    await _con_plan(repos, bruno, semanas=20, distancia=42)
    dia = min(s.fecha for s in plan_de_ana.sesiones_programadas())

    await _enviar(TipoRecordatorio.DIARIO, ana, repos, recordatorios, email, dia)

    correo = email.enviados[0]
    assert correo.destinatario == ana.email
    assert "Bruno" not in correo.texto
    assert "42K" not in correo.texto


# --- Presentacion ---------------------------------------------------------------


def test_el_html_escapa_lo_que_venga_del_runner():
    """El nombre lo escribe el usuario y acaba dentro de un correo HTML."""
    contenido = ContenidoCorreo(asunto="Hoy", parrafos=('<script>alert("x")</script>, esto es lo que toca',))

    html = renderizar_html(PLANTILLA, contenido, "https://koda.test/baja", "https://koda.test")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_el_diario_avisa_cuando_la_carrera_esta_cerca():
    runner = _runner(nombre="Mateo")
    contenido = None
    # Se construye a mano un plan cuya carrera cae dentro de tres semanas
    from app.domain.training.factory import estrategia_para
    from app.domain.training.modelos import Distancia, Objetivo, PlanActivo, fecha_inicio_para

    objetivo = Objetivo(distancia=Distancia.K10, fecha_carrera=HOY + timedelta(weeks=12))
    plan = estrategia_para(Distancia.K10).generar(runner, objetivo, hoy=HOY)
    activo = PlanActivo(
        id=uuid4(),
        objetivo=objetivo,
        plan=plan,
        fecha_inicio=fecha_inicio_para(objetivo, len(plan.semanas), HOY),
        generado_en=datetime(2026, 8, 17),
    )
    cerca = objetivo.fecha_carrera - timedelta(days=10)
    while not [s for s in activo.sesiones_programadas() if s.fecha == cerca]:
        cerca -= timedelta(days=1)

    contenido = redactar_diario(runner, activo, cerca)

    assert contenido is not None
    assert "Mateo" in contenido.parrafos[0]
    assert any("Quedan" in p for p in contenido.parrafos)


def test_como_se_le_cuentan_los_avisos_al_runner():
    semanal = Recordatorio(
        id=uuid4(), runner_id=uuid4(), tipo=TipoRecordatorio.SEMANAL, hora_local=time(19, 30)
    )
    diario = Recordatorio(id=uuid4(), runner_id=uuid4(), tipo=TipoRecordatorio.DIARIO, hora_local=time(6, 0))

    assert "domingos a las 19:30" in descrito(semanal)
    assert "todos los dias a las 06:00" in descrito(diario)

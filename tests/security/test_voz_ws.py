"""WS /ws/voz: mismo principio de auth que el resto de la app — runner_id sale del
JWT de la cookie del handshake, nunca de un parametro del cliente. Ver
docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md y
docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md.

Y desde ADR-020, tambien el reparto entre los dos modelos: Nova Sonic habla, el
modelo grande decide. Los tests de aqui abajo son los que sostienen la promesa de
que la voz no puede inventarse un dato — porque no tiene ninguno.
"""

import asyncio

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.application.coach import HERRAMIENTAS, NOMBRE_HERRAMIENTA_PUENTE
from app.domain.ports.llm_port import LlamadaHerramienta
from app.domain.ports.voz_realtime_port import FragmentoAudio, TranscripcionParcial, TurnoTerminado
from app.interfaces.api import deps
from app.main import app
from tests.fakes.pipeline_voz import FakeLLM
from tests.fakes.repos import (
    InMemoryConversacionRepo,
    InMemoryMemoriaRepo,
    InMemoryPlanRepo,
    InMemoryRecordatorioRepo,
    InMemoryRunnerRepo,
    InMemoryTokenAccesoRepo,
)
from tests.fakes.voz_realtime import FakeVozRealtimePort

_CODIGO_CIERRE_NO_AUTENTICADO = 4401
_CODIGO_CIERRE_FALLBACK = 4500

# Lo que la voz "dice" haber oido cuando se le pide que consulte al entrenador.
CONSULTA = LlamadaHerramienta(
    nombre=NOMBRE_HERRAMIENTA_PUENTE, argumentos={"peticion": "quiero correr un 10k"}
)


def _preparar(voz_fake: FakeVozRealtimePort, *, con_cookie: bool, llm: FakeLLM | None = None) -> TestClient:
    repos = deps.Repos(
        runners=InMemoryRunnerRepo(),
        tokens=InMemoryTokenAccesoRepo(),
        planes=InMemoryPlanRepo(),
        conversaciones=InMemoryConversacionRepo(),
        memoria=InMemoryMemoriaRepo(),
        recordatorios=InMemoryRecordatorioRepo(),
    )
    app.dependency_overrides[deps.get_repos] = lambda: repos
    app.dependency_overrides[deps.get_voz_realtime_port] = lambda: voz_fake
    app.dependency_overrides[deps.get_coach_system_prompt] = lambda: "eres koda"
    # El cerebro va SIEMPRE con doble. Sin este override, el puente al entrenador
    # llamaria al gateway de verdad y la suite dependeria de la red y de AWS.
    app.dependency_overrides[deps.get_llm_port] = lambda: (
        llm or FakeLLM("te armo el 10k", con_herramientas=True)
    )

    cliente = TestClient(app)
    if con_cookie:

        async def _crear_token() -> str:
            runner = await repos.runners.crear_o_actualizar_acceso("voz@example.com")
            settings = deps.get_settings(deps.get_container())
            return deps.crear_jwt(runner.id, settings)

        cliente.cookies.set(deps.COOKIE_NAME, asyncio.run(_crear_token()))
    return cliente


def _hasta_el_final(ws) -> list[dict]:
    recibidos = []
    while True:
        mensaje = ws.receive_json()
        recibidos.append(mensaje)
        if mensaje.get("tipo") == "turno_terminado":
            return recibidos


def _conversacion_guardada() -> list[tuple[str, str]]:
    repos = app.dependency_overrides[deps.get_repos]()
    runner = asyncio.run(repos.runners.obtener_por_email("voz@example.com"))
    return [(m.rol, m.contenido) for m in asyncio.run(repos.conversaciones.ultimos(runner.id))]


# --- Aislamiento ----------------------------------------------------------------


def test_sin_cookie_de_sesion_el_socket_se_cierra_sin_llegar_a_nova_sonic():
    voz_fake = FakeVozRealtimePort()
    cliente = _preparar(voz_fake, con_cookie=False)
    try:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with cliente.websocket_connect("/ws/voz"):
                pass
        assert exc_info.value.code == _CODIGO_CIERRE_NO_AUTENTICADO
        assert voz_fake.sesiones_abiertas == []
    finally:
        app.dependency_overrides.clear()


def test_si_nova_sonic_falla_al_abrir_el_socket_se_cierra_con_codigo_de_fallback():
    voz_fake = FakeVozRealtimePort()
    voz_fake.falla_al_abrir = True
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()
        assert exc_info.value.code == _CODIGO_CIERRE_FALLBACK
    finally:
        app.dependency_overrides.clear()


# --- El reparto entre los dos modelos (ADR-020) ---------------------------------


def test_la_voz_solo_recibe_el_puente_al_entrenador():
    """Antes recibia las cinco herramientas del coach y elegia ella. Elegia mal: con
    una frase ambigua metia la distancia equivocada en crear_plan. Ahora solo puede
    hacer una cosa, y decidir no es esa cosa."""
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[CONSULTA])
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "hola"})
            _hasta_el_final(ws)

        (ofrecidas,) = voz_fake.herramientas_recibidas
        assert [h.nombre for h in ofrecidas] == [NOMBRE_HERRAMIENTA_PUENTE]
        assert "crear_plan" not in [h.nombre for h in ofrecidas]
    finally:
        app.dependency_overrides.clear()


def test_el_prompt_de_la_voz_no_lleva_ni_un_dato_del_runner():
    """Esta es la garantia entera, y por eso es un test y no una nota en un ADR: lo
    que no esta en el contexto no se puede decir equivocado. Si alguien vuelve a
    meterle el contexto a Nova Sonic "para que conteste mas rapido", esto se cae."""
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[CONSULTA])
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "hola"})
            _hasta_el_final(ws)

        (prompt,) = voz_fake.prompts_recibidos
        # Los encabezados que arma construir_system_prompt con los datos del runner.
        for bloque in ("## Ahora mismo", "## Su plan", "## Lo que recuerdas de el", "Hoy es"):
            assert bloque not in prompt, bloque
        # Lo que si tiene: como hablar y a quien preguntarselo todo.
        assert NOMBRE_HERRAMIENTA_PUENTE in prompt
    finally:
        app.dependency_overrides.clear()


def test_la_consulta_llega_al_modelo_grande_con_las_herramientas_de_verdad():
    """El puente no es un adorno: al otro lado esta el coach entero, con el contexto
    del runner y las cinco herramientas que tocan el dominio."""
    llm = FakeLLM("te armo el 10k para el 15 de noviembre", con_herramientas=True)
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[CONSULTA])
    cliente = _preparar(voz_fake, con_cookie=True, llm=llm)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "quiero correr un 10k"})
            _hasta_el_final(ws)

        assert llm.mensajes_recibidos == ["quiero correr un 10k"]
        # El contexto que la voz NO tiene, lo tiene el cerebro.
        assert "Hoy es" in llm.prompts_recibidos[0]
        assert voz_fake.sesiones_abiertas[0].resultados_recibidos == [
            "te armo el 10k para el 15 de noviembre"
        ]
    finally:
        app.dependency_overrides.clear()


def test_si_el_entrenador_se_cae_la_voz_no_improvisa():
    """Antes ninguna respuesta que una inventada — el mismo criterio del ADR-017 con
    los modelos que no ven fotos."""
    llm = FakeLLM(con_herramientas=True)
    llm.falla = True
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[CONSULTA])
    cliente = _preparar(voz_fake, con_cookie=True, llm=llm)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "que me toca hoy"})
            _hasta_el_final(ws)

        (resultado,) = voz_fake.sesiones_abiertas[0].resultados_recibidos
        assert "NO te inventes" in resultado
    finally:
        app.dependency_overrides.clear()


def test_un_turno_sin_consultar_al_entrenador_se_rescata():
    """Si la voz cierra un turno sin preguntar nada, el runner se queda sin respuesta
    — y creyendo que le contestaron, que es igual de malo que una respuesta inventada.
    El turno se rehace desde el servidor con lo que dijo."""
    llm = FakeLLM("hoy te toca descansar", con_herramientas=True)
    voz_fake = FakeVozRealtimePort(
        eventos_a_emitir=[
            TranscripcionParcial(texto="que me toca hoy", rol="usuario", definitiva=True),
            TranscripcionParcial(texto="mmm, dame un segundo", rol="coach", definitiva=True),
            TurnoTerminado(),
        ],
        llamadas_a_emitir=[],  # la voz NO consulta: es lo que se esta probando
    )
    cliente = _preparar(voz_fake, con_cookie=True, llm=llm)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_bytes(b"pcm-del-microfono")
            recibidos = _hasta_el_final(ws)

        # El rescate se consulta con lo que dijo el runner, no con lo que dijo la voz.
        assert llm.mensajes_recibidos == ["que me toca hoy"]
        assert recibidos[-2] == {
            "tipo": "transcripcion",
            "texto": "hoy te toca descansar",
            "rol": "coach",
            "definitiva": True,
        }
        # Y la respuesta buena es la que queda en la memoria.
        assert ("coach", "mmm, dame un segundo hoy te toca descansar") in _conversacion_guardada()
    finally:
        app.dependency_overrides.clear()


def test_un_turno_en_el_que_nadie_dijo_nada_no_se_rescata():
    """Sin pregunta no hay turno que rehacer, y consultar al entrenador con una cadena
    vacia seria gastar una llamada al modelo por cada silencio."""
    llm = FakeLLM(con_herramientas=True)
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[])
    cliente = _preparar(voz_fake, con_cookie=True, llm=llm)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_bytes(b"pcm-del-microfono")
            _hasta_el_final(ws)

        assert llm.mensajes_recibidos == []
    finally:
        app.dependency_overrides.clear()


def test_el_texto_y_la_voz_comparten_las_mismas_herramientas_del_dominio():
    """El reparto cambio, la promesa no: hablar y escribir siguen siendo el mismo Koda
    porque detras hay el mismo cerebro con las mismas cinco herramientas."""
    llm = FakeLLM(con_herramientas=True)
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[CONSULTA])
    cliente = _preparar(voz_fake, con_cookie=True, llm=llm)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "hola"})
            _hasta_el_final(ws)

        assert llm.herramientas_recibidas[0] == HERRAMIENTAS
    finally:
        app.dependency_overrides.clear()


# --- Transcripciones y memoria --------------------------------------------------


def test_un_mensaje_de_texto_llega_a_la_sesion_de_voz():
    """El texto tambien pasa por Nova Sonic (misma voz que el microfono) — el navegador
    lo manda como mensaje de control por el mismo WebSocket."""
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()], llamadas_a_emitir=[CONSULTA])
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "quiero correr un 10k"})
            _hasta_el_final(ws)
        assert voz_fake.sesiones_abiertas[0].texto_recibido == ["quiero correr un 10k"]
    finally:
        app.dependency_overrides.clear()


def test_reenvia_transcripcion_y_audio_al_navegador():
    voz_fake = FakeVozRealtimePort(
        eventos_a_emitir=[
            TranscripcionParcial(texto="hola koda", rol="usuario", definitiva=True),
            FragmentoAudio(datos=b"audio-de-nova-sonic"),
            TurnoTerminado(),
        ],
        llamadas_a_emitir=[CONSULTA],
    )
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_bytes(b"pcm-del-microfono")
            assert ws.receive_json() == {
                "tipo": "transcripcion",
                "texto": "hola koda",
                "rol": "usuario",
                "definitiva": True,
            }
            assert ws.receive_bytes() == b"audio-de-nova-sonic"
            assert ws.receive_json() == {"tipo": "turno_terminado"}
    finally:
        app.dependency_overrides.clear()


def test_reenvia_el_adelanto_y_la_transcripcion_confirmada_marcados_distinto():
    """La interfaz muestra el adelanto enseguida y lo sustituye por la confirmada; para
    poder distinguirlos necesita la marca 'definitiva' — sin ella, en los turnos de voz
    (donde a veces solo llega el adelanto) el chat se quedaba sin el texto de Koda."""
    voz_fake = FakeVozRealtimePort(
        eventos_a_emitir=[
            TranscripcionParcial(texto="voy a decir esto", rol="coach", definitiva=False),
            TranscripcionParcial(texto="esto fue lo que dije", rol="coach", definitiva=True),
        ],
        llamadas_a_emitir=[CONSULTA],
    )
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_bytes(b"pcm-del-microfono")
            adelanto = ws.receive_json()
            confirmada = ws.receive_json()
        assert adelanto["definitiva"] is False
        assert confirmada["definitiva"] is True
        assert confirmada["texto"] == "esto fue lo que dije"
    finally:
        app.dependency_overrides.clear()


def test_el_turno_de_voz_se_guarda_en_la_memoria():
    """Sin esto, cada mensaje abre una sesion en blanco: el runner dice 'maraton' y en
    el mensaje siguiente Koda le pregunta la distancia."""
    voz_fake = FakeVozRealtimePort(
        eventos_a_emitir=[
            TranscripcionParcial(texto="quiero un maraton", rol="usuario", definitiva=True),
            TranscripcionParcial(texto="pensando decir esto", rol="coach", definitiva=False),
            TranscripcionParcial(texto="¿que fecha?", rol="coach", definitiva=True),
            TurnoTerminado(),
        ],
        llamadas_a_emitir=[CONSULTA],
    )
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "quiero un maraton"})
            _hasta_el_final(ws)

        assert _conversacion_guardada() == [
            ("usuario", "quiero un maraton"),
            ("coach", "¿que fecha?"),  # el adelanto NO se guarda: nunca se dijo
        ]
    finally:
        app.dependency_overrides.clear()


def test_si_koda_no_manda_transcripcion_confirmada_se_guarda_el_adelanto():
    """Nova Sonic a menudo no manda nunca la FINAL en turnos de voz. Guardando solo la
    confirmada, la memoria se quedaba con lo que dijo el runner y sin la respuesta —
    una ventana de conversacion coja."""
    voz_fake = FakeVozRealtimePort(
        eventos_a_emitir=[
            TranscripcionParcial(texto="que me toca hoy", rol="usuario", definitiva=True),
            TranscripcionParcial(texto="hoy te toca descansar", rol="coach", definitiva=False),
            TurnoTerminado(),
        ],
        llamadas_a_emitir=[CONSULTA],
    )
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "que me toca hoy"})
            _hasta_el_final(ws)

        assert _conversacion_guardada() == [
            ("usuario", "que me toca hoy"),
            ("coach", "hoy te toca descansar"),
        ]
    finally:
        app.dependency_overrides.clear()

"""WS /ws/voz: mismo principio de auth que el resto de la app — runner_id sale del
JWT de la cookie del handshake, nunca de un parametro del cliente. Ver
docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md y
docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md."""

import asyncio

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.domain.ports.voz_realtime_port import FragmentoAudio, TranscripcionParcial, TurnoTerminado
from app.interfaces.api import deps
from app.main import app
from tests.fakes.repos import InMemoryPlanRepo, InMemoryRunnerRepo, InMemoryTokenAccesoRepo
from tests.fakes.voz_realtime import FakeVozRealtimePort

_CODIGO_CIERRE_NO_AUTENTICADO = 4401
_CODIGO_CIERRE_FALLBACK = 4500


def _preparar(voz_fake: FakeVozRealtimePort, *, con_cookie: bool) -> TestClient:
    repos = deps.Repos(
        runners=InMemoryRunnerRepo(), tokens=InMemoryTokenAccesoRepo(), planes=InMemoryPlanRepo()
    )
    app.dependency_overrides[deps.get_repos] = lambda: repos
    app.dependency_overrides[deps.get_voz_realtime_port] = lambda: voz_fake
    app.dependency_overrides[deps.get_coach_system_prompt] = lambda: "eres koda"

    cliente = TestClient(app)
    if con_cookie:

        async def _crear_token() -> str:
            runner = await repos.runners.crear_o_actualizar_acceso("voz@example.com")
            settings = deps.get_settings(deps.get_container())
            return deps.crear_jwt(runner.id, settings)

        cliente.cookies.set(deps.COOKIE_NAME, asyncio.run(_crear_token()))
    return cliente


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


def test_un_mensaje_de_texto_llega_a_la_sesion_de_voz():
    """El texto tambien pasa por Nova Sonic (misma voz que el microfono) — el navegador
    lo manda como mensaje de control por el mismo WebSocket."""
    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()])
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "quiero correr un 10k"})
            assert ws.receive_json() == {"tipo": "turno_terminado"}
        assert voz_fake.sesiones_abiertas[0].texto_recibido == ["quiero correr un 10k"]
    finally:
        app.dependency_overrides.clear()


def test_reenvia_transcripcion_y_audio_al_navegador():
    voz_fake = FakeVozRealtimePort(
        eventos_a_emitir=[
            TranscripcionParcial(texto="hola koda", rol="usuario", definitiva=True),
            FragmentoAudio(datos=b"audio-de-nova-sonic"),
            TurnoTerminado(),
        ]
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


def test_la_voz_recibe_las_mismas_herramientas_que_el_texto():
    """Hablar y escribir tienen que dar el mismo Koda. Si el WebSocket abriera la sesion
    sin herramientas, pedir un plan por voz solo produciria una promesa."""
    from app.application.coach import HERRAMIENTAS

    voz_fake = FakeVozRealtimePort(eventos_a_emitir=[TurnoTerminado()])
    cliente = _preparar(voz_fake, con_cookie=True)
    try:
        with cliente.websocket_connect("/ws/voz") as ws:
            ws.send_json({"tipo": "mensaje_texto", "texto": "hola"})
            ws.receive_json()
        assert voz_fake.herramientas_recibidas[0] == HERRAMIENTAS
        # Y el prompt lleva el contexto que cambia en cada conversacion, no solo el .md
        assert "Hoy es" in voz_fake.prompts_recibidos[0]
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
        ]
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

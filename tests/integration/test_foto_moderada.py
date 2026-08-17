"""Una foto que no pasa la moderacion no llega al modelo.

El test que importa no es que devuelva un 200 con un mensaje amable: es que el LLM
no la vea. Si llegara igual, la moderacion seria decoracion.
"""

import io

from PIL import Image

from app.interfaces.api import deps
from app.interfaces.api.deps import COOKIE_NAME
from tests.fakes.moderacion import FakeModeracion
from tests.fakes.pipeline_voz import FakeLLM, FakeSTT, FakeTTS


def _como(runner) -> dict[str, str]:
    jwt = deps.crear_jwt(runner.id, deps.get_container().settings)
    return {"Cookie": f"{COOKIE_NAME}={jwt}"}


def _una_foto_de_verdad() -> bytes:
    """Un JPEG valido: tiene que pasar el saneado para llegar a la moderacion."""
    buffer = io.BytesIO()
    Image.new("RGB", (240, 240), (20, 30, 50)).save(buffer, "JPEG")
    return buffer.getvalue()


async def _mandar_foto(cliente, runner) -> object:
    return await cliente.post(
        "/api/mensajes",
        files={"foto": ("reloj.jpg", _una_foto_de_verdad(), "image/jpeg")},
        headers=_como(runner),
    )


async def test_una_foto_rechazada_no_llega_al_modelo(cliente, runner_a):
    from app.main import app

    llm = FakeLLM(con_imagenes=True)
    moderacion = FakeModeracion(rechaza=True)
    app.dependency_overrides[deps.get_llm_port] = lambda: llm
    app.dependency_overrides[deps.get_stt_port] = lambda: FakeSTT()
    app.dependency_overrides[deps.get_tts_port] = lambda: FakeTTS()
    app.dependency_overrides[deps.get_moderacion] = lambda: moderacion
    try:
        resp = await _mandar_foto(cliente, runner_a)

        assert resp.status_code == 200
        assert moderacion.revisadas == 1
        # Lo importante: el modelo no la vio, y no se pago la llamada.
        assert llm.imagenes_recibidas == []
        assert llm.mensajes_recibidos == []
        # Y al runner no se le dice que categoria salto: seria el manual para esquivarla.
        assert "Nudity" not in resp.json()["texto"]
    finally:
        app.dependency_overrides.pop(deps.get_llm_port, None)
        app.dependency_overrides.pop(deps.get_stt_port, None)
        app.dependency_overrides.pop(deps.get_tts_port, None)
        app.dependency_overrides.pop(deps.get_moderacion, None)


async def test_una_foto_limpia_si_llega_al_modelo(cliente, runner_a):
    from app.main import app

    llm = FakeLLM(con_imagenes=True)
    moderacion = FakeModeracion(rechaza=False)
    app.dependency_overrides[deps.get_llm_port] = lambda: llm
    app.dependency_overrides[deps.get_stt_port] = lambda: FakeSTT()
    app.dependency_overrides[deps.get_tts_port] = lambda: FakeTTS()
    app.dependency_overrides[deps.get_moderacion] = lambda: moderacion
    try:
        resp = await _mandar_foto(cliente, runner_a)

        assert resp.status_code == 200
        assert moderacion.revisadas == 1
        assert len(llm.imagenes_recibidas) == 1
    finally:
        app.dependency_overrides.pop(deps.get_llm_port, None)
        app.dependency_overrides.pop(deps.get_stt_port, None)
        app.dependency_overrides.pop(deps.get_tts_port, None)
        app.dependency_overrides.pop(deps.get_moderacion, None)

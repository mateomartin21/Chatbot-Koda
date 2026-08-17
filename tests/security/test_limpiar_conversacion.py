"""Limpiar el chat borra el hilo de UNO, y solo el hilo.

Dos garantias distintas y las dos importan:

1. Aislamiento — un borrado que se llevara por delante las conversaciones de otros
   seria el fallo mas caro del proyecto, porque no se deshace.
2. Alcance — el perfil y los hechos duraderos NO se tocan. "Limpiar el chat" y
   "olvida lo que te conte" son cosas distintas.
"""

from app.domain.models import Hecho, Mensaje
from app.interfaces.api import deps
from app.interfaces.api.deps import COOKIE_NAME


def _como(runner) -> dict[str, str]:
    jwt = deps.crear_jwt(runner.id, deps.get_container().settings)
    return {"Cookie": f"{COOKIE_NAME}={jwt}"}


async def _conversacion_de(repos, runner, cuantos: int = 3) -> None:
    await repos.conversaciones.guardar(
        runner.id,
        [Mensaje(rol="usuario", contenido=f"mensaje {i}", modalidad="texto") for i in range(cuantos)],
    )


async def test_limpiar_no_toca_la_conversacion_de_otro(cliente, repos, runner_a, runner_b):
    await _conversacion_de(repos, runner_a, 3)
    await _conversacion_de(repos, runner_b, 4)

    resp = await cliente.delete("/api/conversacion", headers=_como(runner_a))

    assert resp.status_code == 200
    assert resp.json()["borrados"] == 3
    assert await repos.conversaciones.ultimos(runner_a.id) == []
    assert len(await repos.conversaciones.ultimos(runner_b.id)) == 4


async def test_limpiar_exige_sesion(cliente, repos, runner_a):
    await _conversacion_de(repos, runner_a, 3)

    assert (await cliente.delete("/api/conversacion")).status_code == 401
    assert len(await repos.conversaciones.ultimos(runner_a.id)) == 3


async def test_limpiar_el_chat_no_le_borra_la_memoria_a_koda(cliente, repos, runner_a):
    """Lo que Koda ha aprendido sobrevive. Si esto se pone en rojo, alguien convirtio
    "limpiar la pantalla" en "empezar de cero", que no es lo que promete el boton."""
    await _conversacion_de(repos, runner_a, 3)
    await repos.memoria.guardar(
        runner_a.id, [Hecho(categoria="lesion", hecho="le molesta la rodilla izquierda")]
    )
    perfil_antes = await repos.runners.obtener(runner_a.id)

    await cliente.delete("/api/conversacion", headers=_como(runner_a))

    hechos = await repos.memoria.vigentes(runner_a.id)
    assert [h.hecho for h in hechos] == ["le molesta la rodilla izquierda"]
    assert await repos.runners.obtener(runner_a.id) == perfil_antes


async def test_limpiar_dos_veces_no_se_queja(cliente, runner_a):
    """Idempotente: el segundo clic no es un error, es que ya estaba limpio."""
    primera = await cliente.delete("/api/conversacion", headers=_como(runner_a))
    segunda = await cliente.delete("/api/conversacion", headers=_como(runner_a))
    assert primera.status_code == segunda.status_code == 200
    assert segunda.json()["borrados"] == 0

"""El perfil avisa de lo que no cuadra ANTES de que el runner se ponga a hablar.

El dominio ya se defiende de una marca imposible ignorandola, pero ignorarla en
silencio deja a alguien creyendo que dio su dato. Aqui se comprueba que la API lo dice.
"""

from app.interfaces.api import deps
from app.interfaces.api.deps import COOKIE_NAME


def _como(runner) -> dict[str, str]:
    jwt = deps.crear_jwt(runner.id, deps.get_container().settings)
    return {"Cookie": f"{COOKIE_NAME}={jwt}"}


async def test_una_marca_con_ritmo_imposible_se_rechaza_al_guardar(cliente, runner_a):
    """5 km en 30 segundos: el caso real, escrito sin ":" en un teclado de movil."""
    resp = await cliente.put(
        "/api/perfil",
        json={"marca_distancia_km": 5, "marca_tiempo_seg": 30},
        headers=_como(runner_a),
    )

    assert resp.status_code == 422
    # El mensaje tiene que servirle a una persona, no solo marcar el campo en rojo.
    assert "ritmo imposible" in resp.json()["detail"]
    assert "25:30" in resp.json()["detail"]


async def test_una_marca_absurdamente_lenta_tambien(cliente, runner_a):
    resp = await cliente.put(
        "/api/perfil",
        json={"marca_distancia_km": 5, "marca_tiempo_seg": 25 * 3600},
        headers=_como(runner_a),
    )
    assert resp.status_code == 422


async def test_una_marca_de_verdad_se_guarda_sin_pelear(cliente, runner_a):
    """El aviso no puede volverse tan estricto que estorbe a quien hace las cosas bien."""
    resp = await cliente.put(
        "/api/perfil",
        json={"marca_distancia_km": 5, "marca_tiempo_seg": 25 * 60 + 30},
        headers=_como(runner_a),
    )

    assert resp.status_code == 200
    assert resp.json()["marca_tiempo_seg"] == 25 * 60 + 30


async def test_una_marca_a_medias_no_se_juzga(cliente, runner_a):
    """Solo la distancia, sin tiempo: no hay ritmo que comprobar todavia, y decir que
    es imposible seria mentir. Eso ya lo avisa el formulario por su cuenta."""
    resp = await cliente.put(
        "/api/perfil",
        json={"marca_distancia_km": 5},
        headers=_como(runner_a),
    )
    assert resp.status_code == 200

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
    detalle = resp.json()["detail"]
    # Se señala el campo concreto: sin esto, el formulario solo puede enseñar el aviso
    # al pie y el runner tiene que adivinar cuál de los seis se le da mal.
    assert detalle["campo"] == "perfil-marca-tiempo"
    # Y el mensaje tiene que servirle a una persona, no solo marcar el campo en rojo.
    assert "ritmo imposible" in detalle["mensaje"]
    assert "25:30" in detalle["mensaje"]


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


# --- Lo que intentaron los amigos del autor ---------------------------------------
#
# Cada uno de estos devolvia antes un 422 de pydantic en ingles, del estilo "Input
# should be less than or equal to 100", sin decir que campo mirar.


async def test_cada_dato_imposible_dice_que_campo_es_y_lo_explica_en_castellano(cliente, runner_a):
    intentos = [
        ({"edad": 999}, "perfil-edad"),
        ({"edad": 3}, "perfil-edad"),
        ({"dias_disponibles": 9}, "perfil-dias"),
        ({"dias_disponibles": 0}, "perfil-dias"),
        ({"nivel": "superman"}, "perfil-nivel"),
        ({"marca_distancia_km": 5000}, "perfil-marca-km"),
        ({"marca_distancia_km": 0.2}, "perfil-marca-km"),
        ({"nombre": "x" * 200}, "perfil-nombre"),
    ]
    for cuerpo, campo in intentos:
        resp = await cliente.put("/api/perfil", json=cuerpo, headers=_como(runner_a))
        assert resp.status_code == 422, cuerpo
        detalle = resp.json()["detail"]
        assert detalle["campo"] == campo, cuerpo
        # Escrito para una persona: ni "Input should be", ni el nombre del campo suelto.
        assert detalle["mensaje"][0].isupper() and detalle["mensaje"].endswith(".")


async def test_un_perfil_entero_y_correcto_pasa_sin_una_queja(cliente, runner_a):
    resp = await cliente.put(
        "/api/perfil",
        json={
            "nombre": "Ana",
            "edad": 34,
            "nivel": "intermedio",
            "dias_disponibles": 4,
            "marca_distancia_km": 10,
            "marca_tiempo_seg": 52 * 60 + 30,
        },
        headers=_como(runner_a),
    )
    assert resp.status_code == 200
    assert resp.json()["nombre"] == "Ana"

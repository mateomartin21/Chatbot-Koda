"""El plan de un runner no existe para los demas.

docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2: runner_id sale del JWT y de ningun
otro sitio. Estos tests intentan justo lo contrario y comprueban que no cuela.
"""

from datetime import date, timedelta

from app.interfaces.api import deps
from app.interfaces.api.deps import COOKIE_NAME

EN_DOCE_SEMANAS = (date.today() + timedelta(weeks=13)).isoformat()


def _como(runner) -> dict[str, str]:
    """La sesion de un runner, como cabecera. Se manda por peticion y no en el cliente
    para poder alternar entre dos usuarios dentro del mismo test."""
    jwt = deps.crear_jwt(runner.id, deps.get_container().settings)
    return {"Cookie": f"{COOKIE_NAME}={jwt}"}


async def _crear_plan_de(cliente, runner, **extra):
    return await cliente.post(
        "/api/plan",
        json={"distancia_km": 10, "fecha_carrera": EN_DOCE_SEMANAS, "dias_por_semana": 4, **extra},
        headers=_como(runner),
    )


async def test_el_plan_de_a_no_aparece_en_el_de_b(cliente, runner_a, runner_b):
    creado = await _crear_plan_de(cliente, runner_a)
    assert creado.status_code == 201

    de_a = await cliente.get("/api/plan", headers=_como(runner_a))
    de_b = await cliente.get("/api/plan", headers=_como(runner_b))

    assert de_a.json()["distancia"] == "10K"
    assert de_b.json() is None


async def test_el_plan_exige_sesion(cliente):
    sin_sesion = await cliente.post("/api/plan", json={"distancia_km": 10, "fecha_carrera": EN_DOCE_SEMANAS})
    assert (await cliente.get("/api/plan")).status_code == 401
    assert sin_sesion.status_code == 401


async def test_un_runner_id_en_el_cuerpo_no_cambia_de_dueno(cliente, runner_a, runner_b):
    """El intento de IDOR mas obvio: mandar el id de otro y esperar que alguien lo lea."""
    creado = await _crear_plan_de(cliente, runner_a, runner_id=str(runner_b.id))
    assert creado.status_code == 201

    assert (await cliente.get("/api/plan", headers=_como(runner_b))).json() is None
    assert (await cliente.get("/api/plan", headers=_como(runner_a))).json() is not None


async def test_el_perfil_que_se_guarda_es_el_del_token(cliente, runner_a, runner_b):
    await cliente.put(
        "/api/perfil",
        json={"nombre": "Mateo", "nivel": "avanzado", "runner_id": str(runner_b.id)},
        headers=_como(runner_a),
    )
    perfil_b = await cliente.get("/api/perfil", headers=_como(runner_b))
    assert perfil_b.json()["nombre"] is None

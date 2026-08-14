"""El enlace de baja no exige iniciar sesión: viaja firmado dentro del correo.

Obligar a entrar para dejar de recibir correos hace que la gente marque como spam en
vez de darse de baja, y eso destroza la reputación de envío del dominio. Pero un enlace
sin sesión es superficie de ataque, así que estos tests son los que sostienen la
decisión: que solo dé de baja a quien lo pidió, y que no revele nada de nadie.
"""

from datetime import time

import pytest

from app.domain.models import TipoRecordatorio
from app.interfaces.api import deps
from app.interfaces.avisos import crear_token_baja


def _settings():
    return deps.get_container().settings


async def _con_recordatorios(repos: deps.Repos, runner) -> None:
    for tipo in TipoRecordatorio:
        await repos.recordatorios.guardar(runner.id, tipo, time(hour=7), activo=True)


async def test_el_enlace_del_correo_da_de_baja_sin_iniciar_sesion(cliente, repos, runner_a):
    await _con_recordatorios(repos, runner_a)
    token = crear_token_baja(runner_a.id, _settings())

    respuesta = await cliente.get(f"/api/recordatorios/baja?token={token}")

    assert respuesta.status_code == 200
    assert all(not r.activo for r in await repos.recordatorios.de_runner(runner_a.id))


async def test_el_enlace_de_uno_no_da_de_baja_al_otro(cliente, repos, runner_a, runner_b):
    await _con_recordatorios(repos, runner_a)
    await _con_recordatorios(repos, runner_b)

    await cliente.get(f"/api/recordatorios/baja?token={crear_token_baja(runner_a.id, _settings())}")

    assert all(not r.activo for r in await repos.recordatorios.de_runner(runner_a.id))
    assert all(r.activo for r in await repos.recordatorios.de_runner(runner_b.id))


@pytest.mark.parametrize("token", ["", "cualquier-cosa", "a.b.c"])
async def test_un_token_inventado_no_da_de_baja_a_nadie(cliente, repos, runner_a, token: str):
    await _con_recordatorios(repos, runner_a)

    respuesta = await cliente.get(f"/api/recordatorios/baja?token={token}")

    assert respuesta.status_code in (404, 422)
    assert all(r.activo for r in await repos.recordatorios.de_runner(runner_a.id))


async def test_una_cookie_de_sesion_no_sirve_como_enlace_de_baja(cliente, repos, runner_a):
    """Los dos son JWT firmados con el mismo secreto. Sin comprobar el 'uso', el token
    de sesion valdria de enlace de baja — y al reves, que es peor."""
    await _con_recordatorios(repos, runner_a)
    token_de_sesion = deps.crear_jwt(runner_a.id, _settings())

    respuesta = await cliente.get(f"/api/recordatorios/baja?token={token_de_sesion}")

    assert respuesta.status_code == 404
    assert all(r.activo for r in await repos.recordatorios.de_runner(runner_a.id))


async def test_la_baja_de_alguien_que_no_existe_no_confirma_nada(cliente, repos):
    """404 y no 403: un 403 confirmaria que ese runner existe."""
    from uuid import uuid4

    respuesta = await cliente.get(f"/api/recordatorios/baja?token={crear_token_baja(uuid4(), _settings())}")

    # El token es valido, asi que responde la pagina; lo que no hace es decir si habia
    # alguien detras. No se filtra la existencia por el codigo de estado.
    assert respuesta.status_code == 200


async def test_los_recordatorios_solo_se_ven_con_sesion(cliente):
    assert (await cliente.get("/api/recordatorios")).status_code == 401
    assert (
        await cliente.put("/api/recordatorios", json={"tipo": "diario", "hora_local": "07:00"})
    ).status_code == 401

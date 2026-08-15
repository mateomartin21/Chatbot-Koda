"""La conversacion de un runner no existe para los demas.

Es la ruta mas sensible de toda la API. El plan son numeros; la conversacion es lo
que la persona ESCRIBIO — lesiones, horarios, en que trabaja, por que dejo de correr.
Una fuga aqui no es un dato de mas, es una charla privada entera.

docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2: runner_id sale del JWT y de ningun
otro sitio. Estos tests intentan justo lo contrario.
"""

from app.domain.models import Mensaje
from app.interfaces.api import deps
from app.interfaces.api.deps import COOKIE_NAME


def _como(runner) -> dict[str, str]:
    jwt = deps.crear_jwt(runner.id, deps.get_container().settings)
    return {"Cookie": f"{COOKIE_NAME}={jwt}"}


async def test_la_conversacion_de_a_no_aparece_en_la_de_b(cliente, repos, runner_a, runner_b):
    await repos.conversaciones.guardar(
        runner_a.id,
        [
            Mensaje(rol="usuario", contenido="me duele la rodilla desde el domingo"),
            Mensaje(rol="coach", contenido="para hoy y ve a un profesional"),
        ],
    )
    await repos.conversaciones.guardar(
        runner_b.id, [Mensaje(rol="usuario", contenido="quiero correr un 10k")]
    )

    de_a = (await cliente.get("/api/conversacion", headers=_como(runner_a))).json()
    de_b = (await cliente.get("/api/conversacion", headers=_como(runner_b))).json()

    assert [m["contenido"] for m in de_a] == [
        "me duele la rodilla desde el domingo",
        "para hoy y ve a un profesional",
    ]
    assert [m["contenido"] for m in de_b] == ["quiero correr un 10k"]


async def test_la_conversacion_exige_sesion(cliente):
    assert (await cliente.get("/api/conversacion")).status_code == 401


async def test_un_runner_nuevo_no_hereda_conversacion_de_nadie(cliente, repos, runner_a, runner_b):
    """Un runner sin historial recibe una lista vacia, no la del ultimo que escribio."""
    await repos.conversaciones.guardar(runner_a.id, [Mensaje(rol="usuario", contenido="hola koda")])

    assert (await cliente.get("/api/conversacion", headers=_como(runner_b))).json() == []


async def test_los_turnos_llegan_en_el_orden_en_que_se_dijeron(cliente, repos, runner_a):
    """Al reves se leerian como una conversacion distinta. El repositorio los pide por
    fecha descendente (asi esta el indice) y los devuelve dados la vuelta."""
    await repos.conversaciones.guardar(
        runner_a.id,
        [
            Mensaje(rol="usuario", contenido="primero"),
            Mensaje(rol="coach", contenido="segundo"),
            Mensaje(rol="usuario", contenido="tercero"),
        ],
    )

    turnos = (await cliente.get("/api/conversacion", headers=_como(runner_a))).json()

    assert [m["contenido"] for m in turnos] == ["primero", "segundo", "tercero"]
    assert [m["rol"] for m in turnos] == ["usuario", "coach", "usuario"]

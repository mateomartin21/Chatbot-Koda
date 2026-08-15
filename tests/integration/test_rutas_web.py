"""La portada publica vive en / y la aplicacion en /app/.

Son dos ficheros estaticos servidos por el mismo montaje, asi que nada en Python
falla si se mueven de sitio: la unica forma de enterarse seria abriendo el
navegador. De ahi estos tests — y sobre todo el del enlace magico, que redirige a
/app/ y dejaria al runner mirando la pagina de marketing si alguien lo cambia.

El TestClient se usa SIN "with" a proposito: el ciclo de vida de la app arranca el
scheduler y consulta la base de datos, y estos tests solo miran ficheros estaticos.
Con "with" harian falta Postgres para comprobar que un CSS existe.
"""

import inspect

from starlette.testclient import TestClient

from app.interfaces.api import auth
from app.main import app

cliente = TestClient(app)


def test_la_raiz_sirve_la_portada_publica() -> None:
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "Un entrenador de verdad" in respuesta.text
    # La portada no arranca la aplicacion: si cargara app.js, un visitante sin
    # sesion dispararia peticiones a /api/ solo por mirar la pagina.
    assert "/app.js" not in respuesta.text


def test_app_sirve_la_aplicacion() -> None:
    respuesta = cliente.get("/app/")

    assert respuesta.status_code == 200
    assert "/app.js" in respuesta.text
    assert 'id="pantalla-chat"' in respuesta.text


def test_el_enlace_magico_deja_al_runner_dentro_de_la_aplicacion() -> None:
    """El correo tiene que llevarte al chat, no a la portada."""
    assert '"/app/"' in inspect.getsource(auth.canjear)


def test_los_recursos_compartidos_se_sirven_desde_la_raiz() -> None:
    """Portada y aplicacion comparten hoja de estilos, iconos y fondo: si alguno se
    moviera de sitio, una de las dos se veria sin estilos y nadie se enteraria."""
    for ruta in ("/styles.css", "/landing.css", "/iconos.svg", "/relieve.svg", "/icono.svg"):
        assert cliente.get(ruta).status_code == 200, ruta

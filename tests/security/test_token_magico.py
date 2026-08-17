"""Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §5 — los dos primeros tests de la carpeta.

El primero de estos fijaba lo contrario hasta el ADR-024: que el token fuera de un solo
uso. Se cambio a proposito y con su coste anotado, no por comodidad. Un solo uso suena
mas seguro y en la practica cerraba la puerta: los escaneres de los correos corporativos
abren los enlaces para analizarlos, gastan el unico uso, y quien recibe el correo hace
clic sobre un enlace ya muerto. Cuando el enlace magico es la UNICA forma de entrar, eso
no es una molestia, es no poder entrar.

Lo que sigue protegiendo al token: caduca a los 15 minutos, va atado a una direccion de
correo que hay que controlar, se guarda solo su hash, y pedirlos esta limitado por
correo y por IP.
"""

from datetime import UTC, datetime


async def test_el_token_magico_vale_varias_veces_dentro_de_su_ventana(cliente, token):
    """Que un escaner de correo lo abra antes que tu no te puede dejar fuera."""
    primera = await cliente.get(f"/api/auth/canjear?token={token}", follow_redirects=False)
    segunda = await cliente.get(f"/api/auth/canjear?token={token}", follow_redirects=False)

    assert primera.status_code in (200, 307)
    assert segunda.status_code in (200, 307)
    # Y las dos veces deja sesion, no solo un 307 vacio.
    assert segunda.cookies.get("koda_sesion") or "set-cookie" in {k.lower() for k in segunda.headers}


async def test_el_token_magico_caduca(cliente, token_expirado):
    """La caducidad es ahora lo UNICO que cierra la ventana, asi que mas vale que cierre."""
    respuesta = await cliente.get(f"/api/auth/canjear?token={token_expirado}", follow_redirects=False)
    assert respuesta.status_code == 401


async def test_un_token_caducado_no_revive_por_haberse_usado_antes(cliente, repos, runner_a, token):
    """Canjearlo no lo prorroga: pasada la hora de expiracion deja de valer, punto."""
    await cliente.get(f"/api/auth/canjear?token={token}", follow_redirects=False)

    # Se le adelanta la caducidad como si hubieran pasado los quince minutos.
    import hashlib

    registro = await repos.tokens.obtener_por_hash(hashlib.sha256(token.encode()).hexdigest())
    registro.expira_en = datetime.now(UTC).replace(year=2020)

    caducado = await cliente.get(f"/api/auth/canjear?token={token}", follow_redirects=False)
    assert caducado.status_code == 401


async def test_un_token_inventado_no_entra(cliente):
    respuesta = await cliente.get(
        "/api/auth/canjear?token=esto-me-lo-acabo-de-inventar", follow_redirects=False
    )
    assert respuesta.status_code == 401

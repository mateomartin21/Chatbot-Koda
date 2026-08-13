"""Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §5 — los dos primeros tests de la carpeta."""


async def test_el_token_magico_es_de_un_solo_uso(cliente, token):
    primera = await cliente.get(f"/api/auth/canjear?token={token}", follow_redirects=False)
    assert primera.status_code in (200, 307)

    segunda = await cliente.get(f"/api/auth/canjear?token={token}", follow_redirects=False)
    assert segunda.status_code == 401


async def test_el_token_magico_caduca(cliente, token_expirado):
    respuesta = await cliente.get(f"/api/auth/canjear?token={token_expirado}", follow_redirects=False)
    assert respuesta.status_code == 401

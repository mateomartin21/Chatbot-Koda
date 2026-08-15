"""Convierte la regla hexagonal en una garantia verificada. Ver docs/contexto/01-ARQUITECTURA.md."""

from pathlib import Path

PROHIBIDOS = ("boto3", "sqlalchemy", "fastapi", "requests", "httpx", "groq", "google")


def test_el_dominio_no_depende_de_infraestructura():
    for archivo in Path("app/domain").rglob("*.py"):
        codigo = archivo.read_text(encoding="utf-8")
        for prohibido in PROHIBIDOS:
            assert f"import {prohibido}" not in codigo, (
                f"{archivo} viola la regla hexagonal: importa {prohibido}"
            )


def test_el_contenedor_se_arma_sin_una_sola_credencial():
    """La suite corre sin internet y sin credenciales — es la regla 5 de CLAUDE.md.

    Solo que no era verdad. `deps.py` arma el contenedor AL IMPORTARSE, y un par de
    adaptadores reventaban en su constructor si les faltaba un ajuste. Resultado: sin
    un `.env` al lado, la aplicacion entera no se podia ni importar, y con ella se
    caia media suite. Pasaba en local porque la maquina tenia su `.env`; en CI, que no
    lo tiene, llevaba fallando desde el primer dia sin que nadie lo mirara.

    Construir un adaptador es cablearlo, no usarlo. Que le falte configuracion se
    tiene que notar al usarlo, o al arrancar el servidor — nunca al importar un
    modulo. Este test es lo que mantiene esa frontera en pie."""
    from app.config import Settings
    from app.container import build_container

    vacio = Settings(jwt_secret="x", _env_file=None)

    contenedor = build_container(vacio)

    assert contenedor.stt is not None
    assert contenedor.llm is not None
    assert contenedor.tts is not None
    assert contenedor.voz_realtime is not None


def test_el_arranque_avisa_de_los_ajustes_que_faltan():
    """Lo que se perdio al quitar la validacion de los constructores no se tiro: se
    movio al arranque, que es donde se oye. Si alguien despliega sin SES_FROM_EMAIL,
    el servidor lo dice en vez de descubrirlo en el primer enlace magico."""
    from app.config import Settings
    from app.main import _ajustes_que_faltan

    faltan = _ajustes_que_faltan(Settings(jwt_secret="x", _env_file=None))

    assert any("S3_BUCKET" in f for f in faltan)
    assert any("BEDROCK_MODEL_ID" in f for f in faltan)
    assert any("SES_FROM_EMAIL" in f for f in faltan)

    completo = Settings(
        jwt_secret="x",
        s3_bucket="koda",
        bedrock_model_id="un-modelo",
        ses_from_email="koda@ejemplo.com",
        _env_file=None,
    )
    assert _ajustes_que_faltan(completo) == []

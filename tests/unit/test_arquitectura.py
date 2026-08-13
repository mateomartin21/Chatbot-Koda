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

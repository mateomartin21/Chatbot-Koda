"""La moderacion de fotos: que rechaza, que deja pasar y que hace cuando no puede decidir.

Ninguno de estos tests llama a Rekognition. El adaptador de verdad se prueba por su
contrato — como traduce lo que devuelve el servicio — con la respuesta ya fabricada.
"""

import pytest

from app.config import Settings
from app.domain.ports.llm_port import Imagen
from app.infrastructure.moderacion.rekognition import RekognitionModeracion, SinModeracion

UNA_FOTO = Imagen(datos=b"no importa, no sale de aqui", formato="jpeg")


def _adaptador(respuesta=None, revienta=False) -> RekognitionModeracion:
    """El adaptador con su llamada a AWS sustituida. Se prueba la traduccion, que es
    lo unico que es nuestro: que Rekognition detecte bien es problema de Rekognition."""
    moderacion = RekognitionModeracion(Settings(jwt_secret="x", _env_file=None))

    def falso(datos: bytes) -> dict:
        if revienta:
            raise RuntimeError("Rekognition no responde")
        return respuesta or {}

    moderacion._detectar = falso
    return moderacion


async def test_una_foto_limpia_pasa():
    veredicto = await _adaptador({"ModerationLabels": []}).revisar(UNA_FOTO)
    assert veredicto.apta
    assert veredicto.motivo is None


async def test_una_foto_con_desnudos_no_pasa():
    respuesta = {
        "ModerationLabels": [
            {"Name": "Explicit Nudity", "Confidence": 99.2},
            {"Name": "Graphic Male Nudity", "Confidence": 98.1, "ParentName": "Explicit Nudity"},
        ]
    }
    veredicto = await _adaptador(respuesta).revisar(UNA_FOTO)

    assert not veredicto.apta
    # El motivo es para el log: la categoria de primer nivel, no la hija.
    assert "Explicit Nudity" in veredicto.motivo


async def test_se_queda_con_la_categoria_de_primer_nivel_mas_segura():
    respuesta = {
        "ModerationLabels": [
            {"Name": "Violence", "Confidence": 85.0},
            {"Name": "Explicit Nudity", "Confidence": 97.0},
            {"Name": "Weapon Violence", "Confidence": 84.0, "ParentName": "Violence"},
        ]
    }
    veredicto = await _adaptador(respuesta).revisar(UNA_FOTO)
    assert "Explicit Nudity" in veredicto.motivo


async def test_si_rekognition_no_responde_la_foto_pasa():
    """Decision explicita del ADR-023, no un descuido. Bloquear cada foto de reloj
    porque un servicio auxiliar esta caido rompe la funcion para todo el mundo, y la
    imagen sigue sin guardarse y sigue teniendo enfrente los filtros del modelo."""
    veredicto = await _adaptador(revienta=True).revisar(UNA_FOTO)
    assert veredicto.apta


async def test_con_la_moderacion_apagada_no_se_llama_a_nadie():
    assert (await SinModeracion().revisar(UNA_FOTO)).apta


@pytest.mark.parametrize("encendida", [True, False])
def test_el_contenedor_se_arma_con_y_sin_moderacion(encendida: bool):
    from app.container import build_container

    contenedor = build_container(Settings(jwt_secret="x", moderacion_imagenes=encendida, _env_file=None))
    assert contenedor.moderacion is not None

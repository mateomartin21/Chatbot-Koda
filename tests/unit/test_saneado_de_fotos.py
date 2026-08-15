"""El saneado de fotos es la frontera de privacidad de la aplicacion.

Una foto de movil lleva EXIF, y el EXIF lleva las coordenadas GPS de donde se saco.
El runner fotografia el reloj al terminar de correr, o sea, en su calle. Estos tests
existen para que nadie quite el reprocesado por hacerlo "mas rapido".
"""

import io

import pytest
from PIL import Image

from app.infrastructure.imagenes.sanitizar import (
    LADO_MAXIMO,
    ImagenInvalida,
    sanear,
)


def _jpeg(ancho: int = 800, alto: int = 600, exif: bytes | None = None) -> bytes:
    imagen = Image.new("RGB", (ancho, alto), (30, 40, 60))
    destino = io.BytesIO()
    if exif is not None:
        imagen.save(destino, format="JPEG", exif=exif)
    else:
        imagen.save(destino, format="JPEG")
    return destino.getvalue()


def _jpeg_con_gps() -> bytes:
    """Una foto con coordenadas dentro, como la que sale de cualquier telefono."""
    exif = Image.Exif()
    exif[0x0110] = "Pixel 8"  # modelo del telefono
    exif[0x8825] = {
        1: "N",
        2: (20.0, 40.0, 0.0),  # latitud: grados, minutos, segundos
        3: "W",
        4: (103.0, 21.0, 0.0),  # longitud
    }
    return _jpeg(exif=exif.tobytes())


def test_la_foto_saneada_no_lleva_gps_ni_modelo_de_telefono() -> None:
    original = _jpeg_con_gps()
    assert Image.open(io.BytesIO(original)).getexif(), "la foto de partida deberia traer EXIF"

    limpia = sanear(original)

    metadatos = Image.open(io.BytesIO(limpia.datos)).getexif()
    assert not metadatos, f"la foto saneada todavia lleva metadatos: {dict(metadatos)}"


def test_una_foto_enorme_se_reduce() -> None:
    limpia = sanear(_jpeg(4032, 3024))

    imagen = Image.open(io.BytesIO(limpia.datos))
    assert max(imagen.size) <= LADO_MAXIMO
    # Y sigue siendo la misma foto, no un recorte: la proporcion se conserva.
    assert abs(imagen.width / imagen.height - 4032 / 3024) < 0.01


def test_siempre_sale_jpeg_aunque_entre_png() -> None:
    origen = io.BytesIO()
    Image.new("RGBA", (300, 200), (255, 0, 0, 128)).save(origen, format="PNG")

    limpia = sanear(origen.getvalue())

    assert limpia.formato == "jpeg"
    assert Image.open(io.BytesIO(limpia.datos)).format == "JPEG"


def test_lo_que_no_es_una_imagen_se_rechaza_aqui_y_no_mas_adelante() -> None:
    with pytest.raises(ImagenInvalida):
        sanear(b"#!/bin/sh\nrm -rf /\n")


def test_un_archivo_vacio_se_rechaza() -> None:
    with pytest.raises(ImagenInvalida):
        sanear(b"")


def test_una_foto_vertical_llega_derecha() -> None:
    """La orientacion vive en el EXIF, que se tira. Si no se aplica antes de tirarlo,
    el modelo intenta leer la pantalla de un reloj tumbada."""
    exif = Image.Exif()
    exif[0x0112] = 6  # "girada 90 grados"
    alta = _jpeg(600, 800, exif=exif.tobytes())

    limpia = sanear(alta)

    imagen = Image.open(io.BytesIO(limpia.datos))
    assert imagen.width > imagen.height, "la rotacion del EXIF no se aplico antes de tirarlo"

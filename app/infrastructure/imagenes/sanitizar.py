"""Saneado de las fotos que sube el runner, antes de que salgan del servidor.

Esto no es una optimizacion: es la frontera de privacidad de la aplicacion. Una
foto sacada con el movil lleva EXIF, y el EXIF lleva **las coordenadas GPS del
sitio donde se saco**. Un runner fotografia la pantalla del reloj al terminar de
correr, es decir, en su calle o en su casa. Reenviar ese archivo tal cual a
Bedrock seria mandarle a un tercero donde vive alguien que solo queria apuntar
sus kilometros.

Reprocesar la imagen resuelve tres problemas de un golpe:

1. **Metadatos.** Pillow abre los pixeles y vuelve a codificar. Lo que no son
   pixeles — EXIF, GPS, marca del telefono, miniatura incrustada — no sobrevive.
2. **Archivos con sorpresa.** Lo que entra se decodifica de verdad; lo que no sea
   una imagen valida revienta aqui, dentro de un try, y no mas adelante.
3. **Coste y latencia.** Una foto de movil son 12 MP y varios MB. Para leer los
   numeros de la pantalla de un reloj sobra con 1600 px de lado.

Ver docs/adr/ADR-017-la-foto-se-reprocesa-antes-de-salir.md.
"""

import io
import logging

from PIL import Image, ImageOps

from app.domain.ports.llm_port import Imagen

logger = logging.getLogger(__name__)

# Bedrock acepta hasta 3,75 MB por imagen; se corta muy por debajo porque a partir
# de cierto tamano no se lee mejor un reloj, solo se paga mas y se tarda mas.
LADO_MAXIMO = 1600
CALIDAD = 82
BYTES_MAXIMOS_ENTRADA = 12 * 1024 * 1024

# Lo que Pillow sabe abrir y ademas tiene sentido que llegue de una camara. No se
# acepta cualquier cosa que Pillow reconozca: menos formatos, menos superficie.
FORMATOS_ACEPTADOS = frozenset({"JPEG", "PNG", "WEBP", "HEIF", "HEIC", "MPO"})


class ImagenInvalida(Exception):
    """Lo que subieron no es una imagen que podamos usar."""


def sanear(datos: bytes) -> Imagen:
    """Devuelve un JPEG limpio, sin metadatos y de tamano razonable.

    Lanza ImagenInvalida si lo que llega no se puede decodificar como imagen.
    """
    if not datos:
        raise ImagenInvalida("El archivo esta vacio")
    if len(datos) > BYTES_MAXIMOS_ENTRADA:
        raise ImagenInvalida(f"La imagen pesa mas de {BYTES_MAXIMOS_ENTRADA // (1024 * 1024)} MB")

    try:
        with Image.open(io.BytesIO(datos)) as original:
            formato = (original.format or "").upper()
            if formato not in FORMATOS_ACEPTADOS:
                raise ImagenInvalida(f"Formato no admitido: {formato or 'desconocido'}")

            # exif_transpose ANTES de tirar el EXIF: la orientacion vive ahi, y sin
            # esto una foto sacada en vertical llega girada y el modelo intenta leer
            # un reloj de lado.
            imagen = ImageOps.exif_transpose(original)
            imagen = imagen.convert("RGB")
            imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.Resampling.LANCZOS)

            destino = io.BytesIO()
            # Sin exif= ni icc_profile=: lo que no se pasa aqui, no viaja.
            imagen.save(destino, format="JPEG", quality=CALIDAD, optimize=True)
    except ImagenInvalida:
        raise
    except Exception as error:  # noqa: BLE001 — cualquier fallo de decodificacion
        raise ImagenInvalida("No se pudo leer la imagen") from error

    limpia = destino.getvalue()
    logger.info(
        "Foto saneada: %d KB -> %d KB (%s -> JPEG)",
        len(datos) // 1024,
        len(limpia) // 1024,
        formato,
    )
    return Imagen(datos=limpia, formato="jpeg")

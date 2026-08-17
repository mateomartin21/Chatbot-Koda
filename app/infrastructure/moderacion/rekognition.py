"""Moderacion de imagenes con Amazon Rekognition.

DetectModerationLabels devuelve categorias jerarquicas ("Explicit Nudity" ->
"Graphic Male Nudity") con una confianza cada una. Solo se miran las de primer nivel:
son las que estan definidas de forma estable entre versiones del modelo.

Requiere el permiso rekognition:DetectModerationLabels, que NO viene con el resto de
la politica de Koda. Sin el, esta clase deja pasar la imagen y lo registra — ver el
razonamiento en ADR-023.
"""

import asyncio
import logging

from app.config import Settings
from app.domain.ports.llm_port import Imagen
from app.domain.ports.moderacion_port import ModeracionImagenPort, Veredicto
from app.infrastructure.aws_session import cliente_aws

logger = logging.getLogger(__name__)


class RekognitionModeracion(ModeracionImagenPort):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cliente = None

    def _obtener_cliente(self):
        # Perezoso, como el resto de adaptadores: construir el cliente en __init__
        # obliga a tener credenciales para armar el contenedor, y hay un test que
        # comprueba que se arma sin ninguna.
        if self._cliente is None:
            self._cliente = cliente_aws("rekognition", self._settings)
        return self._cliente

    async def revisar(self, imagen: Imagen) -> Veredicto:
        try:
            respuesta = await asyncio.to_thread(self._detectar, imagen.datos)
        except Exception:  # noqa: BLE001 — degradar, no bloquear (ADR-023)
            logger.warning("Rekognition no pudo revisar la imagen; se deja pasar", exc_info=True)
            return Veredicto.pasa()

        etiquetas = respuesta.get("ModerationLabels", [])
        # La de primer nivel es la que no tiene padre. Es la categoria estable.
        principales = [e for e in etiquetas if not e.get("ParentName")]
        if not principales:
            return Veredicto.pasa()

        peor = max(principales, key=lambda e: e.get("Confidence", 0))
        motivo = f"{peor.get('Name')} ({peor.get('Confidence', 0):.0f}%)"
        logger.info("Imagen rechazada por moderacion: %s", motivo)
        return Veredicto.rechazada(motivo)

    def _detectar(self, datos: bytes) -> dict:
        return self._obtener_cliente().detect_moderation_labels(
            Image={"Bytes": datos},
            MinConfidence=self._settings.moderacion_min_confianza,
        )


class SinModeracion(ModeracionImagenPort):
    """Cuando la moderacion esta apagada. Objeto nulo, para que el endpoint no tenga
    que preguntar si existe: un `if` menos en el camino de cada foto."""

    async def revisar(self, imagen: Imagen) -> Veredicto:
        return Veredicto.pasa()

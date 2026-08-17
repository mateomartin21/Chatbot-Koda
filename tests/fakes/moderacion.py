"""Doble de la moderacion de imagenes. Nunca llama a Rekognition."""

from app.domain.ports.llm_port import Imagen
from app.domain.ports.moderacion_port import ModeracionImagenPort, Veredicto


class FakeModeracion(ModeracionImagenPort):
    def __init__(self, *, rechaza: bool = False, motivo: str = "Explicit Nudity (99%)") -> None:
        self.rechaza = rechaza
        self.motivo = motivo
        self.revisadas = 0

    async def revisar(self, imagen: Imagen) -> Veredicto:
        self.revisadas += 1
        return Veredicto.rechazada(self.motivo) if self.rechaza else Veredicto.pasa()


class ModeracionQueRevienta(ModeracionImagenPort):
    """El servicio caido o un permiso que falta. El adaptador de verdad traduce esto a
    'pasa' (ADR-023); este doble lanza para poder probar quien lo aguanta."""

    async def revisar(self, imagen: Imagen) -> Veredicto:
        raise RuntimeError("Rekognition no responde")

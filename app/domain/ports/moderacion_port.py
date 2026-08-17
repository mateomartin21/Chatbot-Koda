"""Puerto de moderacion de imagenes.

Koda pide fotos de la pantalla de un reloj. Nada impide que llegue otra cosa, y una
foto ilegal o sexual no es un caso hipotetico cuando la aplicacion es publica y el
enlace se comparte.

La imagen NO se guarda en ningun sitio (ver ADR-017 y ADR-023), asi que el riesgo de
alojar contenido no existe. Lo que este puerto añade es un criterio propio ANTES de
gastar la llamada al modelo, en vez de depender solo de que el proveedor se niegue.

Sin imports externos, como todo lo que vive en app/domain — lo comprueba
tests/unit/test_arquitectura.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.ports.llm_port import Imagen


@dataclass(frozen=True)
class Veredicto:
    """Si la imagen puede seguir su camino, y por que no si no puede.

    `motivo` es la etiqueta cruda del proveedor y va al log, nunca al runner: decirle
    a alguien exactamente que categoria salto es escribirle el manual para esquivarla.
    """

    apta: bool
    motivo: str | None = None

    @classmethod
    def pasa(cls) -> "Veredicto":
        return cls(apta=True)

    @classmethod
    def rechazada(cls, motivo: str) -> "Veredicto":
        return cls(apta=False, motivo=motivo)


class ModeracionImagenPort(ABC):
    @abstractmethod
    async def revisar(self, imagen: Imagen) -> Veredicto:
        """Decide si la imagen puede salir hacia el modelo.

        Una implementacion que no pueda decidir —el servicio caido, un permiso que
        falta— devuelve `pasa()`. Es una decision explicita y esta razonada en el
        ADR-023: bloquear cada foto de reloj porque un servicio auxiliar no responde
        rompe la funcion de verdad para todo el mundo, y la imagen sigue sin guardarse
        y sigue teniendo enfrente los filtros del modelo.
        """
        ...

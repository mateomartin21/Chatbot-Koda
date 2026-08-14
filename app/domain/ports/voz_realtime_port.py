"""Puerto de conversacion de voz en tiempo real (Nova Sonic). A diferencia de
STTPort/LLMPort/TTSPort (llamadas sin estado), un turno de voz en tiempo real es
un flujo continuo con estado — de ahi la sesion en vez de un metodo unico.
Ver docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta


@dataclass
class TranscripcionParcial:
    texto: str
    rol: str  # "usuario" | "coach"
    # False = adelanto de lo que el modelo piensa decir (llega junto con el audio).
    # True = transcripcion confirmada de lo que realmente dijo. La confirmada puede no
    # llegar nunca, asi que la interfaz muestra el adelanto y lo sustituye si llega.
    definitiva: bool = False


@dataclass
class FragmentoAudio:
    datos: bytes


@dataclass
class TurnoTerminado:
    pass


@dataclass
class ErrorSesion:
    mensaje: str


EventoVoz = TranscripcionParcial | FragmentoAudio | TurnoTerminado | ErrorSesion


class SesionVozRealtime(ABC):
    @abstractmethod
    async def enviar_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def enviar_texto(self, texto: str) -> None:
        """Turno de texto en la misma sesion (Nova Sonic acepta texto ademas de audio,
        "cross-modal input") — se manda como un unico bloque, sin streaming."""
        ...

    @abstractmethod
    async def terminar_turno_audio(self) -> None:
        """Senaliza que el usuario dejo de hablar (sin cerrar la sesion) — el modelo
        necesita esto para saber que ya le toca responder. Sin esto, cerrar la sesion
        entera al parar de grabar mata la respuesta antes de que llegue."""
        ...

    @abstractmethod
    def eventos(self) -> AsyncIterator[EventoVoz]: ...

    @abstractmethod
    async def cerrar(self) -> None: ...


class VozRealtimePort(ABC):
    @abstractmethod
    async def abrir_sesion(
        self,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
    ) -> SesionVozRealtime:
        """Las herramientas se declaran al abrir la sesion, no por turno: en un flujo
        bidireccional no hay un punto donde volver a negociarlas. La sesion las ejecuta
        por dentro — quien consume eventos() no se entera de que hubo una llamada."""
        ...

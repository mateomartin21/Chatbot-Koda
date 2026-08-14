"""Dobles del pipeline de voz. Sin red — ver docs/contexto/08-CONVENCIONES.md."""

import asyncio
from collections.abc import Sequence

from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, LlamadaHerramienta, LLMPort
from app.domain.ports.stt_port import STTPort
from app.domain.ports.tts_port import TTSPort


class FakeSTT(STTPort):
    def __init__(self, transcripcion: str = "hola koda") -> None:
        self.transcripcion = transcripcion
        self.falla = False

    async def transcribir(self, audio: bytes, audio_mime: str) -> str:
        if self.falla:
            raise RuntimeError("STT no disponible")
        return self.transcripcion


class FakeLLM(LLMPort):
    def __init__(self, respuesta: str = "hola, soy koda", *, con_herramientas: bool = False) -> None:
        self.respuesta = respuesta
        self.falla = False
        self.retraso_segundos = 0.0  # para probar timeouts del gateway sin red real
        self.mensajes_recibidos: list[str] = []
        self.prompts_recibidos: list[str] = []
        self._con_herramientas = con_herramientas
        # Herramientas que este doble "decide" llamar antes de contestar, en orden.
        self.llamadas_a_emitir: list[LlamadaHerramienta] = []
        self.resultados_recibidos: list[str] = []

    @property
    def soporta_herramientas(self) -> bool:
        return self._con_herramientas

    async def conversar(
        self,
        mensaje_usuario: str,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
    ) -> str:
        self.mensajes_recibidos.append(mensaje_usuario)
        self.prompts_recibidos.append(system_prompt)
        if self.retraso_segundos:
            await asyncio.sleep(self.retraso_segundos)
        if self.falla:
            raise RuntimeError("LLM no disponible")
        if ejecutar is not None:
            for llamada in self.llamadas_a_emitir:
                self.resultados_recibidos.append(await ejecutar(llamada))
        return self.respuesta


class FakeTTS(TTSPort):
    def __init__(self, audio: bytes = b"audio-falso") -> None:
        self.audio = audio
        self.falla = False

    async def sintetizar(self, texto: str) -> bytes:
        if self.falla:
            raise RuntimeError("TTS no disponible")
        return self.audio

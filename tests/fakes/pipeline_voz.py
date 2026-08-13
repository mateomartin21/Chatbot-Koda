"""Dobles del pipeline de voz. Sin red — ver docs/contexto/08-CONVENCIONES.md."""

from app.domain.ports.llm_port import LLMPort
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
    def __init__(self, respuesta: str = "hola, soy koda") -> None:
        self.respuesta = respuesta
        self.falla = False
        self.mensajes_recibidos: list[str] = []

    async def conversar(self, mensaje_usuario: str, *, system_prompt: str) -> str:
        self.mensajes_recibidos.append(mensaje_usuario)
        if self.falla:
            raise RuntimeError("LLM no disponible")
        return self.respuesta


class FakeTTS(TTSPort):
    def __init__(self, audio: bytes = b"audio-falso") -> None:
        self.audio = audio
        self.falla = False

    async def sintetizar(self, texto: str) -> bytes:
        if self.falla:
            raise RuntimeError("TTS no disponible")
        return self.audio

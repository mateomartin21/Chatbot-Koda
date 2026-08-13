"""Puerto de texto a voz. La implementacion concreta (Polly, Gemini TTS...) vive en infrastructure/."""

from abc import ABC, abstractmethod


class TTSPort(ABC):
    @abstractmethod
    async def sintetizar(self, texto: str) -> bytes: ...

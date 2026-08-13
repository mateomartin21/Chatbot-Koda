"""Puerto de voz a texto. La implementacion concreta (Transcribe, Groq Whisper...) vive en infrastructure/."""

from abc import ABC, abstractmethod


class STTPort(ABC):
    @abstractmethod
    async def transcribir(self, audio: bytes, audio_mime: str) -> str: ...

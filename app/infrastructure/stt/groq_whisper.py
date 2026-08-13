"""Adaptador de STTPort sobre la API de Whisper alojada en Groq.
Plan B temporal mientras Amazon Transcribe esta bloqueado por la cuenta nueva —
ver docs/adr/ADR-009-groq-stt-temporal.md."""

import httpx

from app.config import Settings
from app.domain.ports.stt_port import STTPort

_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqWhisperSTT(STTPort):
    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY no esta configurada")
        self._api_key = settings.groq_api_key
        self._modelo = settings.groq_stt_model
        self._idioma = settings.transcribe_language.split("-")[0]  # "es-MX" -> "es"

    async def transcribir(self, audio: bytes, audio_mime: str) -> str:
        extension = audio_mime.split("/")[-1] if "/" in audio_mime else "wav"
        async with httpx.AsyncClient(timeout=30.0) as client:
            respuesta = await client.post(
                _URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": (f"audio.{extension}", audio, audio_mime)},
                data={"model": self._modelo, "language": self._idioma},
            )
            respuesta.raise_for_status()
            return respuesta.json()["text"].strip()

"""Adaptador de TTSPort sobre Amazon Polly."""

import asyncio

from app.config import Settings
from app.domain.ports.tts_port import TTSPort
from app.infrastructure.aws_session import cliente_aws


class PollyTTS(TTSPort):
    def __init__(self, settings: Settings) -> None:
        self._client = cliente_aws("polly", settings)
        self._voice_id = settings.polly_voice_id
        self._engine = settings.polly_engine
        self._output_format = settings.polly_output_format

    async def sintetizar(self, texto: str) -> bytes:
        return await asyncio.to_thread(self._sintetizar_sync, texto)

    def _sintetizar_sync(self, texto: str) -> bytes:
        respuesta = self._client.synthesize_speech(
            Text=texto,
            OutputFormat=self._output_format,
            VoiceId=self._voice_id,
            Engine=self._engine,
        )
        return respuesta["AudioStream"].read()

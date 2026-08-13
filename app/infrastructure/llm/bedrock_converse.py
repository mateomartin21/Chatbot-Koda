"""Adaptador de LLMPort sobre la Converse API de Amazon Bedrock."""

import asyncio

from app.config import Settings
from app.domain.ports.llm_port import LLMPort
from app.infrastructure.aws_session import cliente_aws


class BedrockConverse(LLMPort):
    def __init__(self, settings: Settings) -> None:
        self._client = cliente_aws("bedrock-runtime", settings)
        self._model_id = settings.bedrock_model_id

    async def conversar(self, mensaje_usuario: str, *, system_prompt: str) -> str:
        return await asyncio.to_thread(self._conversar_sync, mensaje_usuario, system_prompt)

    def _conversar_sync(self, mensaje_usuario: str, system_prompt: str) -> str:
        respuesta = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": mensaje_usuario}]}],
        )
        return respuesta["output"]["message"]["content"][0]["text"].strip()

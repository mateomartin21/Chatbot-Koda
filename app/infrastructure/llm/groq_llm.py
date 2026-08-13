"""Adaptador de LLMPort sobre la API de chat de Groq.
Segundo proveedor real (no solo segundo modelo) para el gateway de fallback —
ver docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md."""

import httpx

from app.config import Settings
from app.domain.ports.llm_port import LLMPort

_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqLLM(LLMPort):
    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY no esta configurada")
        self._api_key = settings.groq_api_key
        self._modelo = settings.groq_llm_model

    async def conversar(self, mensaje_usuario: str, *, system_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            respuesta = await client.post(
                _URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._modelo,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": mensaje_usuario},
                    ],
                },
            )
            respuesta.raise_for_status()
            return respuesta.json()["choices"][0]["message"]["content"].strip()

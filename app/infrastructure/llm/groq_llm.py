"""Adaptador de LLMPort sobre la API de chat de Groq.
Segundo proveedor real (no solo segundo modelo) para el gateway de fallback —
ver docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md."""

from collections.abc import Sequence

import httpx

from app.config import Settings
from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, Imagen, LLMPort

_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqLLM(LLMPort):
    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY no esta configurada")
        self._api_key = settings.groq_api_key
        self._modelo = settings.groq_llm_model

    # Este tier existe para que la conversacion no se caiga si AWS falla, no para
    # generar planes. Declararlo asi hace que el gateway no le mande herramientas:
    # ignorarlas en silencio seria peor, porque el modelo prometeria un plan que
    # nadie ha creado.
    @property
    def soporta_herramientas(self) -> bool:
        return False

    # El modelo de texto de Groq no ve. Decirlo hace que el gateway se lo salte
    # cuando hay foto, en vez de dejarle contestar sobre una imagen que no ha visto.
    @property
    def soporta_imagenes(self) -> bool:
        return False

    async def conversar(
        self,
        mensaje_usuario: str,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
        imagen: Imagen | None = None,
    ) -> str:
        if herramientas:
            raise NotImplementedError("GroqLLM no implementa tool use")
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

"""Puerto de razonamiento conversacional. La implementacion concreta (Bedrock, Gemini...)
vive en infrastructure/. Sin tool use todavia — llega con la memoria en el Dia 2
(ver docs/contexto/06-PROMPTS.md §4)."""

from abc import ABC, abstractmethod


class LLMPort(ABC):
    @abstractmethod
    async def conversar(self, mensaje_usuario: str, *, system_prompt: str) -> str: ...

"""Adaptador de LLMPort sobre la Converse API de Amazon Bedrock."""

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from app.config import Settings
from app.domain.ports.llm_port import (
    EjecutorHerramientas,
    Herramienta,
    LlamadaHerramienta,
    LLMPort,
)
from app.infrastructure.aws_session import cliente_aws

logger = logging.getLogger(__name__)


class BedrockConverse(LLMPort):
    def __init__(self, settings: Settings, model_id: str | None = None) -> None:
        self._client = cliente_aws("bedrock-runtime", settings)
        self._model_id = model_id or settings.bedrock_model_id
        self._max_iteraciones = settings.bedrock_max_tool_iterations

    @property
    def soporta_herramientas(self) -> bool:
        return True

    async def conversar(
        self,
        mensaje_usuario: str,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
    ) -> str:
        mensajes: list[dict[str, Any]] = [{"role": "user", "content": [{"text": mensaje_usuario}]}]

        # Tope de iteraciones (06-PROMPTS.md §4): sin el, un modelo que se encabezona
        # llamando herramientas dispara coste y latencia sin que nadie lo pare.
        for iteracion in range(self._max_iteraciones):
            respuesta = await asyncio.to_thread(self._invocar, system_prompt, mensajes, herramientas)
            salida = respuesta["output"]["message"]
            mensajes.append(salida)

            llamadas = _llamadas_de(salida)
            if not llamadas or ejecutar is None:
                return _texto_de(salida)

            resultados = []
            for identificador, llamada in llamadas:
                resultado = await ejecutar(llamada)
                resultados.append(
                    {"toolResult": {"toolUseId": identificador, "content": [{"text": resultado}]}}
                )
            mensajes.append({"role": "user", "content": resultados})
            logger.info("Iteracion %d de herramientas: %d llamada(s)", iteracion + 1, len(llamadas))

        # Se agotaron las iteraciones con el modelo todavia pidiendo herramientas. Se
        # le da una ultima oportunidad de hablar, ya sin ellas, en vez de devolver el
        # ultimo toolResult en crudo al usuario.
        ultima = await asyncio.to_thread(self._invocar, system_prompt, mensajes, ())
        return _texto_de(ultima["output"]["message"])

    def _invocar(
        self, system_prompt: str, mensajes: list[dict[str, Any]], herramientas: Sequence[Herramienta]
    ) -> dict[str, Any]:
        parametros: dict[str, Any] = {
            "modelId": self._model_id,
            # coach_system.md es identico en cada request -> candidato perfecto para
            # prompt caching de Bedrock (~10% del costo en cache hit). Si el prompt no
            # llega al minimo de tokens del modelo, Bedrock simplemente no cachea.
            "system": [{"text": system_prompt}, {"cachePoint": {"type": "default"}}],
            "messages": mensajes,
        }
        if herramientas:
            parametros["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": h.nombre,
                            "description": h.descripcion,
                            "inputSchema": {"json": h.esquema},
                        }
                    }
                    for h in herramientas
                ]
            }
        return self._client.converse(**parametros)


def _llamadas_de(mensaje: dict[str, Any]) -> list[tuple[str, LlamadaHerramienta]]:
    return [
        (
            bloque["toolUse"]["toolUseId"],
            LlamadaHerramienta(
                nombre=bloque["toolUse"]["name"], argumentos=bloque["toolUse"].get("input") or {}
            ),
        )
        for bloque in mensaje.get("content", [])
        if "toolUse" in bloque
    ]


def _texto_de(mensaje: dict[str, Any]) -> str:
    # Un mensaje puede traer varios bloques de texto (y bloques de razonamiento que no
    # son texto): se juntan todos en vez de asumir que el primero es la respuesta.
    return " ".join(b["text"].strip() for b in mensaje.get("content", []) if "text" in b).strip()

"""Model gateway: unifica varios LLMPort detras de uno solo, con fallback ordenado.

Patron de "model gateway" de AI Engineering (Chip Huyen) — no reintenta la misma
llamada, prueba proveedores/modelos distintos en orden hasta que uno responde.
El gateway no sabe de espanol ni de UX: si todos los tiers fallan, propaga la
ultima excepcion y deja que app/application/procesar_mensaje.py decida el mensaje
de degradacion (misma separacion de responsabilidades que ya sigue ese archivo).
Ver docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md.
"""

import asyncio
import logging

from app.domain.ports.llm_port import LLMPort

logger = logging.getLogger(__name__)

_TIMEOUT_POR_INTENTO_SEGUNDOS = 4.0


class ModelGatewayLLM(LLMPort):
    def __init__(
        self, tiers: list[LLMPort], *, timeout_segundos: float = _TIMEOUT_POR_INTENTO_SEGUNDOS
    ) -> None:
        if not tiers:
            raise ValueError("ModelGatewayLLM necesita al menos un tier")
        self._tiers = tiers
        self._timeout = timeout_segundos

    async def conversar(self, mensaje_usuario: str, *, system_prompt: str) -> str:
        ultimo_error: Exception | None = None
        for indice, tier in enumerate(self._tiers):
            try:
                return await asyncio.wait_for(
                    tier.conversar(mensaje_usuario, system_prompt=system_prompt),
                    timeout=self._timeout,
                )
            except Exception as error:  # noqa: BLE001 — probar el siguiente tier, no morir aqui
                logger.warning("Tier %d/%d del LLM gateway fallo: %s", indice + 1, len(self._tiers), error)
                ultimo_error = error
        assert ultimo_error is not None  # hay al menos un tier (validado en __init__), el bucle corrio
        raise ultimo_error

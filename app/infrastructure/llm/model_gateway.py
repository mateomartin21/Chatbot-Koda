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
from collections.abc import Sequence

from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, Imagen, LLMPort

logger = logging.getLogger(__name__)

_TIMEOUT_POR_INTENTO_SEGUNDOS = 4.0
# Con herramientas hace falta mas margen: un turno son varias llamadas al modelo mas
# la ejecucion de la herramienta entre medias, no una sola ida y vuelta.
_TIMEOUT_CON_HERRAMIENTAS_SEGUNDOS = 20.0


class ModelGatewayLLM(LLMPort):
    def __init__(
        self, tiers: list[LLMPort], *, timeout_segundos: float = _TIMEOUT_POR_INTENTO_SEGUNDOS
    ) -> None:
        if not tiers:
            raise ValueError("ModelGatewayLLM necesita al menos un tier")
        self._tiers = tiers
        self._timeout = timeout_segundos

    @property
    def soporta_herramientas(self) -> bool:
        return any(tier.soporta_herramientas for tier in self._tiers)

    @property
    def soporta_imagenes(self) -> bool:
        return any(tier.soporta_imagenes for tier in self._tiers)

    async def conversar(
        self,
        mensaje_usuario: str,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
        imagen: Imagen | None = None,
    ) -> str:
        # Con foto solo entran los tiers que ven. Un modelo ciego recibiria el texto
        # que la acompana ("registra esto") y contestaria como si la hubiera mirado:
        # el runner se creeria que su entrenamiento quedo apuntado. Antes ninguna
        # respuesta que una inventada.
        if imagen is not None:
            return await self._probar(
                [t for t in self._tiers if t.soporta_imagenes],
                mensaje_usuario,
                system_prompt,
                herramientas if self.soporta_herramientas else (),
                ejecutar,
                timeout=_TIMEOUT_CON_HERRAMIENTAS_SEGUNDOS,
                imagen=imagen,
            )

        if herramientas:
            capaces = [t for t in self._tiers if t.soporta_herramientas]
            try:
                return await self._probar(
                    capaces,
                    mensaje_usuario,
                    system_prompt,
                    herramientas,
                    ejecutar,
                    timeout=_TIMEOUT_CON_HERRAMIENTAS_SEGUNDOS,
                )
            except Exception:  # noqa: BLE001
                # Ningun modelo con herramientas responde. Antes que dejar al runner sin
                # contestacion, se conversa con los que quedan: no podran crear un plan,
                # y el prompt les obliga a decirlo en vez de inventarselo.
                logger.warning("Ningun tier con herramientas respondio; se degrada a conversacion")
                restantes = [t for t in self._tiers if not t.soporta_herramientas]
                if not restantes:
                    raise
                return await self._probar(restantes, mensaje_usuario, system_prompt, (), None)

        return await self._probar(self._tiers, mensaje_usuario, system_prompt, (), None)

    async def _probar(
        self,
        tiers: Sequence[LLMPort],
        mensaje_usuario: str,
        system_prompt: str,
        herramientas: Sequence[Herramienta],
        ejecutar: EjecutorHerramientas | None,
        timeout: float | None = None,
        imagen: Imagen | None = None,
    ) -> str:
        if not tiers:
            raise RuntimeError("No hay ningun tier disponible para esta llamada")
        ultimo_error: Exception | None = None
        for indice, tier in enumerate(tiers):
            try:
                return await asyncio.wait_for(
                    tier.conversar(
                        mensaje_usuario,
                        system_prompt=system_prompt,
                        herramientas=herramientas,
                        ejecutar=ejecutar,
                        imagen=imagen,
                    ),
                    timeout=timeout or self._timeout,
                )
            except Exception as error:  # noqa: BLE001 — probar el siguiente tier, no morir aqui
                logger.warning("Tier %d/%d del LLM gateway fallo: %s", indice + 1, len(tiers), error)
                ultimo_error = error
        assert ultimo_error is not None  # la lista no esta vacia, el bucle corrio
        raise ultimo_error

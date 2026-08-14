"""Puerto de razonamiento conversacional. La implementacion concreta (Bedrock, Groq...)
vive en infrastructure/.

El LLM conversa; el dominio calcula. Las herramientas son el unico punto donde el
modelo puede provocar un calculo real, y ninguna recibe runner_id: se lo inyecta el
ejecutor desde la sesion autenticada. Si el modelo pudiera elegir el runner_id, bastaria
convencerlo por prompt para leer los datos de otro — ver 03-MULTIUSUARIO §4.2.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Herramienta:
    """Lo que el modelo puede pedir que se ejecute. El esquema es JSON Schema."""

    nombre: str
    descripcion: str
    esquema: dict[str, Any]


@dataclass(frozen=True)
class LlamadaHerramienta:
    nombre: str
    argumentos: dict[str, Any]


# El resultado vuelve al modelo como texto plano y no como JSON: lo unico que va a
# hacer con el es contarlo en voz alta, y un modelo leyendo JSON en voz alta suena
# a modelo leyendo JSON en voz alta.
EjecutorHerramientas = Callable[[LlamadaHerramienta], Awaitable[str]]


class LLMPort(ABC):
    @abstractmethod
    async def conversar(
        self,
        mensaje_usuario: str,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
    ) -> str: ...

    @property
    def soporta_herramientas(self) -> bool:
        """Un adaptador que no sabe de herramientas y recibe unas debe decirlo, no
        ignorarlas en silencio: el modelo prometeria un plan que nadie ha creado."""
        return False

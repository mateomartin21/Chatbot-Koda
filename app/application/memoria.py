"""Capa 3 de la memoria: extraer de la conversacion lo que trasciende la sesion.

Se ejecuta DESPUES de responder al usuario y nunca en el camino critico: la latencia
es el argumento del proyecto y una llamada de mas por turno se nota. Si falla, se
pierde un hecho — no una respuesta.

Usa un modelo pequeno y barato porque esto es clasificacion, no razonamiento
(docs/contexto/05-MEMORIA.md §5).
"""

import json
import logging
import re
from collections.abc import Sequence

from pydantic import BaseModel, Field, ValidationError

from app.domain.models import Hecho, Mensaje
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.repositories import MemoriaRepo

logger = logging.getLogger(__name__)

CATEGORIAS_VALIDAS = ("lesion", "preferencia", "contexto", "logro", "restriccion")

# Por debajo de esto el modelo esta adivinando, y un plan condicionado por una
# suposicion es peor que un plan sin ella.
_CONFIANZA_MINIMA = 0.5
_MAX_HECHOS_POR_TURNO = 5


class _HechoExtraido(BaseModel):
    """Validacion estricta: si el modelo devuelve algo raro, se descarta entero.

    Una memoria vacia es mejor que una memoria corrupta — lo segundo se le cuenta al
    runner como si fuera verdad.
    """

    categoria: str
    hecho: str = Field(min_length=3, max_length=300)
    confianza: float = Field(default=1.0, ge=0.0, le=1.0)


def _extraer_json(respuesta: str) -> str:
    """Los modelos pequenos envuelven el JSON en ```json o lo preceden de un "Aqui
    tienes:". Se busca el array en vez de exigir una respuesta limpia."""
    sin_vallas = re.sub(r"```(?:json)?|```", "", respuesta).strip()
    inicio, fin = sin_vallas.find("["), sin_vallas.rfind("]")
    return sin_vallas[inicio : fin + 1] if inicio != -1 and fin > inicio else sin_vallas


def parsear_hechos(respuesta: str) -> list[Hecho]:
    try:
        crudos = json.loads(_extraer_json(respuesta))
    except (json.JSONDecodeError, TypeError):
        logger.warning("La extraccion de memoria no devolvio JSON valido: %r", respuesta[:200])
        return []
    if not isinstance(crudos, list):
        return []

    hechos: list[Hecho] = []
    for crudo in crudos[:_MAX_HECHOS_POR_TURNO]:
        try:
            validado = _HechoExtraido.model_validate(crudo)
        except (ValidationError, TypeError):
            continue
        categoria = validado.categoria.strip().lower()
        if categoria not in CATEGORIAS_VALIDAS or validado.confianza < _CONFIANZA_MINIMA:
            continue
        hechos.append(Hecho(categoria=categoria, hecho=validado.hecho.strip(), confianza=validado.confianza))
    return hechos


def _transcribir(mensajes: Sequence[Mensaje]) -> str:
    return "\n".join(f"{'Corredor' if m.rol == 'usuario' else 'Entrenador'}: {m.contenido}" for m in mensajes)


async def extraer_y_guardar(
    runner_id,
    mensajes: Sequence[Mensaje],
    memoria: MemoriaRepo,
    llm: LLMPort,
    prompt_extraccion: str,
) -> int:
    """Devuelve cuantos hechos NUEVOS se guardaron. Nunca lanza: es trabajo de fondo."""
    del_runner = [m for m in mensajes if m.rol == "usuario"]
    if not del_runner or sum(len(m.contenido) for m in del_runner) < 15:
        return 0  # un "hola" o un "sí" no traen nada que recordar

    try:
        respuesta = await llm.conversar(_transcribir(mensajes), system_prompt=prompt_extraccion)
        hechos = parsear_hechos(respuesta)
        if not hechos:
            return 0
        guardados = await memoria.guardar(runner_id, hechos)
    except Exception:  # noqa: BLE001 — se pierde un hecho, no una conversacion
        logger.warning("Fallo la extraccion de memoria", exc_info=True)
        return 0

    if guardados:
        logger.info("Memoria: %d hecho(s) nuevo(s) de %d extraido(s)", guardados, len(hechos))
    return guardados

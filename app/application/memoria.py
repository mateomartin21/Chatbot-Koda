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

from app.domain.models import Hecho, Mensaje, normalizar_hecho
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


# Cortesias puras: lo unico que de verdad no merece gastar una llamada. Antes esto era
# un minimo de caracteres, y descartaba "la rodilla" — diez caracteres y justo el dato
# que habia que recordar. La longitud no mide contenido.
_SIN_CONTENIDO = frozenset(
    {
        "hola",
        "holi",
        "buenas",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "gracias",
        "muchas gracias",
        "ok",
        "okay",
        "vale",
        "va",
        "si",
        "no",
        "claro",
        "perfecto",
        "adios",
        "hasta luego",
        "nos vemos",
    }
)


def _merece_una_llamada(mensajes: Sequence[Mensaje]) -> bool:
    """La extraccion cuesta dinero en cada turno; un saludo no trae nada que recordar."""
    dicho = [normalizar_hecho(m.contenido) for m in mensajes if m.rol == "usuario"]
    return any(texto and texto not in _SIN_CONTENIDO for texto in dicho)


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
    if not _merece_una_llamada(mensajes):
        return 0

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

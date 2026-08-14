"""Las herramientas del coach: el unico punto donde el modelo provoca un calculo real.

Cada una llama a un caso de uso que valida contra el dominio, asi que aunque el modelo
pida un maraton en seis semanas, PlanNoViable lo frena.

Ninguna herramienta recibe runner_id. El ejecutor se construye con el runner ya
autenticado y lo inyecta el mismo — ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md
§4.2 y docs/contexto/06-PROMPTS.md §4.

El contexto que acompana a estas herramientas se ensambla en contexto.py.
"""

import json
import logging
from datetime import date

from app.application.contexto import ReposDelCoach, perfil_hablado, plan_hablado
from app.application.planes import (
    DatosDelPlan,
    consultar_plan_activo,
    consultar_proxima_sesion,
    crear_plan,
)
from app.domain.models import DatosPerfil, Runner
from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, LlamadaHerramienta
from app.domain.training.modelos import PlanNoViable, ValorInvalido
from app.domain.training.paces import Ritmo

logger = logging.getLogger(__name__)

# --- Herramientas ---------------------------------------------------------------

HERRAMIENTAS: tuple[Herramienta, ...] = (
    Herramienta(
        nombre="crear_plan",
        descripcion=(
            "Genera y guarda un plan de entrenamiento para una carrera. Usala cuando el "
            "runner quiera preparar una distancia concreta en una fecha concreta. Si la "
            "fecha no da tiempo, la herramienta lo rechaza y te propone una alternativa: "
            "no insistas ni inventes un plan por tu cuenta."
        ),
        esquema={
            "type": "object",
            "properties": {
                "distancia_km": {"type": "number", "enum": [5, 10, 21, 42]},
                # El dia y el mes van por separado, y el anio NO es obligatorio, a
                # proposito. Con un unico campo "AAAA-MM-DD" el modelo se sentia obligado
                # a averiguar el anio y lo preguntaba, por mucho que el prompt le dijera
                # que no — tres intentos por prompt no lo evitaron. Partiendo el campo,
                # la pregunta deja de tener sentido: no hay hueco que rellenar.
                "dia": {"type": "integer", "minimum": 1, "maximum": 31},
                "mes": {"type": "integer", "minimum": 1, "maximum": 12},
                "anio": {
                    "type": "integer",
                    "description": (
                        "Solo si el runner lo dijo. Si no, omitelo: se toma la proxima vez que ocurra."
                    ),
                },
                "dias_por_semana": {"type": "integer", "minimum": 2, "maximum": 7},
                "nombre_carrera": {"type": "string"},
                "tiempo_meta_seg": {"type": "number", "description": "en segundos, opcional"},
            },
            "required": ["distancia_km", "dia", "mes"],
        },
    ),
    Herramienta(
        nombre="consultar_plan",
        descripcion="Devuelve el plan activo del runner y la siguiente sesion que le toca.",
        esquema={"type": "object", "properties": {}},
    ),
    Herramienta(
        nombre="guardar_datos_del_runner",
        descripcion=(
            "Guarda lo que el runner cuente sobre si mismo: nombre, edad, nivel, cuantos "
            "dias puede correr, o una marca reciente. Usala en cuanto lo mencione, sin "
            "pedirle permiso. Manda solo los campos que te haya dicho."
        ),
        esquema={
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "edad": {"type": "integer", "minimum": 10, "maximum": 100},
                "nivel": {"type": "string", "enum": ["principiante", "intermedio", "avanzado"]},
                "dias_disponibles": {"type": "integer", "minimum": 2, "maximum": 7},
                "marca_distancia_km": {"type": "number"},
                "marca_tiempo_seg": {"type": "number", "description": "en segundos"},
            },
        },
    ),
)


def _fecha_de_la_carrera(argumentos: dict, hoy: date) -> date:
    """Dia y mes obligatorios, anio opcional: sin el, la proxima vez que ocurra.

    Nadie dice "quince de diciembre de dos mil veintiseis" en voz alta. Se acepta
    tambien "fecha_carrera" en ISO porque los modelos improvisan y mandarla entera es
    la improvisacion mas probable; rechazarla obligaria a un turno de mas por un dato
    que ya esta ahi.
    """
    if (iso := argumentos.get("fecha_carrera")) is not None:
        texto = str(iso).strip().lstrip("-")
        try:
            return date.fromisoformat(texto)
        except ValueError:
            return _con_anio_deducido(date.fromisoformat(f"{hoy.year}-{texto}"), hoy)

    dia, mes = int(argumentos["dia"]), int(argumentos["mes"])
    if (anio := argumentos.get("anio")) is not None:
        return date(int(anio), mes, dia)
    return _con_anio_deducido(date(hoy.year, mes, dia), hoy)


def _con_anio_deducido(fecha: date, hoy: date) -> date:
    return fecha if fecha >= hoy else fecha.replace(year=fecha.year + 1)


async def _crear_plan(runner: Runner, repos: ReposDelCoach, argumentos: dict, hoy: date) -> str:
    try:
        fecha_carrera = _fecha_de_la_carrera(argumentos, hoy)
    except (KeyError, TypeError, ValueError):
        return "Falta el dia o el mes de la carrera. Preguntaselo al runner (el anio no hace falta)."

    try:
        activo = await crear_plan(
            runner=runner,
            datos=DatosDelPlan(
                distancia_km=float(argumentos["distancia_km"]),
                fecha_carrera=fecha_carrera,
                dias_por_semana=argumentos.get("dias_por_semana"),
                nombre_carrera=argumentos.get("nombre_carrera"),
                tiempo_meta_seg=argumentos.get("tiempo_meta_seg"),
            ),
            runners=repos.runners,
            planes=repos.planes,
            hoy=hoy,
        )
    except PlanNoViable as no_viable:
        # R6. Que el sistema se niegue no es un error: es la respuesta, y viaja con
        # una alternativa concreta para que el coach tenga algo que ofrecer.
        alternativa = no_viable.alternativa
        return (
            f"RECHAZADO: {no_viable} No se ha creado ningun plan. "
            f"Propone al runner un {alternativa.distancia.etiqueta} en su lugar: {alternativa.motivo} "
            f"Si acepta, vuelve a llamar a crear_plan con distancia_km "
            f"{alternativa.distancia.km:.0f}."
        )
    except (ValorInvalido, KeyError, TypeError, ValueError) as invalido:
        return f"No se pudo crear el plan: {invalido}"

    proxima = await consultar_proxima_sesion(runner.id, repos.planes, hoy=hoy)
    return plan_hablado(activo, proxima, hoy)


async def _consultar_plan(runner: Runner, repos: ReposDelCoach, hoy: date) -> str:
    activo = await consultar_plan_activo(runner.id, repos.planes)
    if activo is None:
        return (
            "Este runner no tiene ningun plan activo. Preguntale que carrera quiere preparar y para cuando."
        )
    proxima = await consultar_proxima_sesion(runner.id, repos.planes, hoy=hoy)
    return plan_hablado(activo, proxima, hoy)


async def _guardar_datos(runner: Runner, repos: ReposDelCoach, argumentos: dict) -> str:
    permitidos = {
        "nombre",
        "edad",
        "nivel",
        "dias_disponibles",
        "marca_distancia_km",
        "marca_tiempo_seg",
    }
    datos = DatosPerfil(**{k: v for k, v in argumentos.items() if k in permitidos and v is not None})
    actualizado = await repos.runners.actualizar_perfil(runner.id, datos)
    respuesta = "Guardado. " + perfil_hablado(actualizado)
    if actualizado.marca_distancia_km and actualizado.marca_tiempo_seg:
        umbral = Ritmo(actualizado.marca_tiempo_seg / actualizado.marca_distancia_km)
        respuesta += f" Su marca sale a {umbral}."
    return respuesta


def ejecutor_para(runner: Runner, repos: ReposDelCoach, hoy: date | None = None) -> EjecutorHerramientas:
    """Ata las herramientas a UN runner concreto. El modelo solo elige el nombre y los
    argumentos; de quien son los datos lo decide este cierre, no la conversacion."""
    dia = hoy or date.today()

    async def ejecutar(llamada: LlamadaHerramienta) -> str:
        logger.info("Herramienta %s(%s)", llamada.nombre, json.dumps(llamada.argumentos, default=str))
        # Se relee en cada llamada porque el turno tipico son DOS: primero el modelo
        # guarda lo que le acaban de contar y despues pide el plan. Con el runner
        # capturado al abrir el turno, ese plan se calcularia con el perfil de antes
        # — es decir, con los ritmos equivocados.
        actual = await repos.runners.obtener(runner.id) or runner

        if llamada.nombre == "crear_plan":
            return await _crear_plan(actual, repos, llamada.argumentos, dia)
        if llamada.nombre == "consultar_plan":
            return await _consultar_plan(actual, repos, dia)
        if llamada.nombre == "guardar_datos_del_runner":
            return await _guardar_datos(actual, repos, llamada.argumentos)
        return f"No existe ninguna herramienta llamada {llamada.nombre}."

    return ejecutar

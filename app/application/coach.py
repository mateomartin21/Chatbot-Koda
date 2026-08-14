"""Lo que el coach sabe y lo que puede hacer.

Dos cosas viven aqui:

1. El contexto que se le mete al system prompt (hoy que dia es, quien es el runner).
   Sin la fecha, "quiero correr en noviembre" no se puede convertir en un objetivo;
   sin el perfil, Koda vuelve a preguntar en cada conversacion lo que ya le dijeron.
2. Las herramientas. Cada una es una llamada a un caso de uso que valida contra el
   dominio: aunque el modelo pida un maraton en seis semanas, PlanNoViable lo frena.

Ninguna herramienta recibe runner_id. El ejecutor se construye con el runner ya
autenticado y lo inyecta el mismo — ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md
§4.2 y docs/contexto/06-PROMPTS.md §4.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date

from app.application.planes import (
    DatosDelPlan,
    consultar_plan_activo,
    consultar_proxima_sesion,
    crear_plan,
)
from app.domain.models import DatosPerfil, Runner
from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, LlamadaHerramienta
from app.domain.ports.repositories import PlanRepo, RunnerRepo
from app.domain.training.modelos import (
    Nivel,
    PlanActivo,
    PlanNoViable,
    SesionProgramada,
    TipoSesion,
    ValorInvalido,
)
from app.domain.training.paces import Ritmo

logger = logging.getLogger(__name__)

_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass
class ReposDelCoach:
    """Lo minimo que necesitan las herramientas. Se pasa asi y no el Repos entero de
    la API para que esta capa no dependa de FastAPI."""

    runners: RunnerRepo
    planes: PlanRepo


# --- Contexto del prompt --------------------------------------------------------


def _fecha_hablada(dia: date) -> str:
    return f"{_DIAS[dia.weekday()]} {dia.day} de {_MESES[dia.month - 1]} de {dia.year}"


def _perfil_hablado(runner: Runner) -> str:
    partes: list[str] = []
    if runner.nombre:
        partes.append(f"Se llama {runner.nombre}")
    if runner.edad:
        partes.append(f"tiene {runner.edad} anios")
    if runner.nivel:
        partes.append(f"se declara de nivel {Nivel.desde_texto(runner.nivel).value}")
    if runner.dias_disponibles:
        partes.append(f"puede correr {runner.dias_disponibles} dias por semana")
    if runner.marca_distancia_km and runner.marca_tiempo_seg:
        minutos, segundos = divmod(round(runner.marca_tiempo_seg), 60)
        partes.append(
            f"su mejor marca reciente es {runner.marca_distancia_km} km en {minutos}:{segundos:02d}"
        )
    if not partes:
        return "Todavia no sabes nada de este runner: ni nivel, ni marcas, ni cuantos dias puede correr."
    return "Lo que sabes de el: " + ", ".join(partes) + "."


def construir_system_prompt(base: str, runner: Runner, hoy: date | None = None) -> str:
    """El prompt de app/prompts/ + lo que cambia en cada conversacion.

    Se concatena aqui y no se guarda en el .md porque el .md es identico en cada
    request — que es justo lo que permite cachearlo en Bedrock. Lo variable va detras.
    """
    return "\n\n".join(
        [
            base.strip(),
            "## Contexto de esta conversacion",
            f"Hoy es {_fecha_hablada(hoy or date.today())}.",
            _perfil_hablado(runner),
        ]
    )


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
                "fecha_carrera": {"type": "string", "description": "AAAA-MM-DD"},
                "dias_por_semana": {"type": "integer", "minimum": 2, "maximum": 7},
                "nombre_carrera": {"type": "string"},
                "tiempo_meta_seg": {"type": "number", "description": "en segundos, opcional"},
            },
            "required": ["distancia_km", "fecha_carrera"],
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


def _sesion_hablada(programada: SesionProgramada) -> str:
    sesion = programada.sesion
    cuando = f"{_DIAS[sesion.dia_semana]} {programada.fecha.day} de {_MESES[programada.fecha.month - 1]}"
    if sesion.tipo is TipoSesion.DESCANSO:
        return f"{cuando}: descanso"
    return f"{cuando}: {sesion.descripcion}"


def _plan_hablado(activo: PlanActivo, proxima: SesionProgramada | None) -> str:
    plan = activo.plan
    volumenes = [s.volumen_km for s in plan.semanas]
    lineas = [
        f"Plan de {activo.objetivo.distancia.etiqueta} guardado: {len(plan.semanas)} semanas, "
        f"del {_fecha_hablada(activo.fecha_inicio)} al {_fecha_hablada(activo.objetivo.fecha_carrera)}.",
        f"Empieza en {volumenes[0]:.0f} km por semana y llega a {max(volumenes):.0f} km.",
        f"Ritmos: facil {plan.zonas.facil}, tirada larga {plan.zonas.larga}, "
        f"tempo {plan.zonas.tempo}, series {plan.zonas.intervalos}.",
    ]
    descargas = [s.numero for s in plan.semanas if s.es_descarga]
    if descargas:
        lineas.append(f"Semanas de descarga: {', '.join(str(n) for n in descargas)}.")
    if plan.ritmos_estimados:
        lineas.append(
            "IMPORTANTE: los ritmos son estimados porque no hay una marca reciente. "
            "Diselo al runner y pidele una."
        )
    lineas.extend(plan.notas)
    if proxima:
        lineas.append(f"Siguiente sesion — {_sesion_hablada(proxima)}.")
    return " ".join(lineas)


async def _crear_plan(runner: Runner, repos: ReposDelCoach, argumentos: dict, hoy: date) -> str:
    try:
        fecha_carrera = date.fromisoformat(str(argumentos["fecha_carrera"]))
    except (KeyError, ValueError):
        return "La fecha de la carrera tiene que venir como AAAA-MM-DD. Preguntasela al runner."

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
    return _plan_hablado(activo, proxima)


async def _consultar_plan(runner: Runner, repos: ReposDelCoach, hoy: date) -> str:
    activo = await consultar_plan_activo(runner.id, repos.planes)
    if activo is None:
        return (
            "Este runner no tiene ningun plan activo. Preguntale que carrera quiere preparar y para cuando."
        )
    proxima = await consultar_proxima_sesion(runner.id, repos.planes, hoy=hoy)
    return _plan_hablado(activo, proxima)


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
    respuesta = "Guardado. " + _perfil_hablado(actualizado)
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

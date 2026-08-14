"""El UNICO sitio que ensambla el contexto del LLM (docs/contexto/05-MEMORIA.md §3).

Tres capas con propositos distintos, no un historial:

1. Perfil y plan — hechos duros, exactos, de coste fijo. Si el runner corre 4 dias,
   eso es una columna INTEGER, no una memoria difusa que el modelo pueda malinterpretar.
2. Ventana corta — los ultimos turnos tal cual, para que los pronombres tengan
   referente ("¿y ese dia que hago?").
3. Hechos duraderos — lo que trasciende la sesion.

Que todas las capas tengan tamano acotado es el argumento entero del diseno: el coste
por mensaje es practicamente constante aunque el runner lleve un anio usando la app.

TODAS las consultas llevan runner_id. Esta funcion es la frontera de aislamiento de
docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.3 — y el sitio donde se audita
cualquier sospecha de fuga entre usuarios.
"""

from dataclasses import dataclass
from datetime import date

from app.domain.models import Hecho, Mensaje, Runner
from app.domain.ports.repositories import ConversacionRepo, MemoriaRepo, PlanRepo, RunnerRepo
from app.domain.training.modelos import Nivel, PlanActivo, SesionProgramada, TipoSesion

_TURNOS_DE_LA_VENTANA = 10
_HECHOS_VIGENTES = 25

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
    """Lo que necesitan el contexto y las herramientas. Se pasa asi, y no el Repos
    entero de la API, para que esta capa no dependa de FastAPI."""

    runners: RunnerRepo
    planes: PlanRepo
    conversaciones: ConversacionRepo
    memoria: MemoriaRepo


@dataclass(frozen=True)
class ContextoConversacion:
    runner: Runner
    hoy: date
    plan: PlanActivo | None
    proxima_sesion: SesionProgramada | None
    recientes: list[Mensaje]
    hechos: list[Hecho]


# --- Formato hablado ------------------------------------------------------------
#
# Todo lo que va al prompt se escribe como se diria en voz alta. El modelo lo va a
# leer a un usuario que esta corriendo: "5:42/km" se lee fatal, "cinco cuarenta y dos"
# es lo que hay que decir, y para eso conviene no darle simbolos que traducir.


def fecha_hablada(dia: date) -> str:
    return f"{_DIAS[dia.weekday()]} {dia.day} de {_MESES[dia.month - 1]} de {dia.year}"


def sesion_hablada(programada: SesionProgramada) -> str:
    sesion = programada.sesion
    cuando = f"{_DIAS[sesion.dia_semana]} {programada.fecha.day} de {_MESES[programada.fecha.month - 1]}"
    if sesion.tipo is TipoSesion.DESCANSO:
        return f"{cuando}: descanso"
    return f"{cuando}: {sesion.descripcion}"


def plan_hablado(activo: PlanActivo, proxima: SesionProgramada | None) -> str:
    plan = activo.plan
    volumenes = [s.volumen_km for s in plan.semanas]
    lineas = [
        f"Plan de {activo.objetivo.distancia.etiqueta} guardado: {len(plan.semanas)} semanas, "
        f"del {fecha_hablada(activo.fecha_inicio)} al {fecha_hablada(activo.objetivo.fecha_carrera)}.",
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
        lineas.append(f"Siguiente sesion — {sesion_hablada(proxima)}.")
    return " ".join(lineas)


def perfil_hablado(runner: Runner) -> str:
    partes: list[str] = []
    if runner.nombre:
        partes.append(f"se llama {runner.nombre}")
    if runner.edad:
        partes.append(f"tiene {runner.edad} anios")
    if runner.nivel:
        partes.append(f"nivel {Nivel.desde_texto(runner.nivel).value}")
    if runner.dias_disponibles:
        partes.append(f"puede correr {runner.dias_disponibles} dias por semana")
    if runner.marca_distancia_km and runner.marca_tiempo_seg:
        minutos, segundos = divmod(round(runner.marca_tiempo_seg), 60)
        partes.append(f"su mejor marca es {runner.marca_distancia_km} km en {minutos}:{segundos:02d}")
    elif runner.marca_distancia_km:
        # Media marca es peor que ninguna: sin el tiempo no hay ritmo que calcular, y
        # el plan saldria con ritmos estimados sin que nadie sepa por que.
        partes.append(
            f"dijo que corrio {runner.marca_distancia_km} km pero NO en cuanto tiempo "
            "(preguntaselo: sin el tiempo no hay ritmos reales)"
        )

    if not partes:
        return "No sabes nada de este runner todavia. Preguntale su nivel y cuantos dias puede correr."
    return "Ya sabes de el: " + ", ".join(partes) + ". NO se lo vuelvas a preguntar."


# --- Ensamblado -----------------------------------------------------------------


async def construir_contexto(
    runner: Runner, repos: ReposDelCoach, hoy: date | None = None
) -> ContextoConversacion:
    dia = hoy or date.today()
    return ContextoConversacion(
        runner=runner,
        hoy=dia,
        plan=await repos.planes.obtener_activo(runner.id),
        proxima_sesion=await repos.planes.proxima_sesion(runner.id, dia),
        recientes=await repos.conversaciones.ultimos(runner.id, _TURNOS_DE_LA_VENTANA),
        hechos=await repos.memoria.vigentes(runner.id, _HECHOS_VIGENTES),
    )


def construir_system_prompt(base: str, contexto: ContextoConversacion) -> str:
    """El prompt de app/prompts/ mas las tres capas.

    El contexto va DELANTE del prompt largo, no detras. Puesto al final, Nova Sonic lo
    ignoraba: preguntaba el anio de una fecha teniendo la de hoy, y volvia a pedir los
    dias por semana que el runner acababa de guardar. Es un modelo pequeno de tiempo
    real y atiende mucho peor al final de tres mil caracteres. Verificado contra el
    modelo real, no deducido.
    """
    bloques = [
        "## Ahora mismo",
        f"Hoy es {fecha_hablada(contexto.hoy)}. Si te dan una fecha sin anio, es la proxima vez "
        f"que ocurra. Nunca preguntes en que anio estamos.",
        perfil_hablado(contexto.runner),
    ]

    if contexto.plan is not None:
        bloques.append("## Su plan\n" + plan_hablado(contexto.plan, contexto.proxima_sesion))
    else:
        bloques.append("No tiene ningun plan activo todavia.")

    if contexto.hechos:
        # Se le dice al modelo de donde salen: son cosas que el runner conto, no
        # verdades absolutas. Con eso las usa con naturalidad en vez de recitarlas.
        recordado = "\n".join(f"- ({h.categoria}) {h.hecho}" for h in contexto.hechos)
        bloques.append(
            "## Lo que recuerdas de el\nTe lo conto en conversaciones anteriores. Usalo "
            "cuando venga a cuento, sin recitarlo.\n" + recordado
        )

    if contexto.recientes:
        # La ventana corta va como texto, no como turnos de la API: en Nova Sonic el
        # system prompt es lo unico que se manda al abrir la sesion, y asi los dos
        # caminos comparten exactamente el mismo contexto.
        transcripcion = "\n".join(
            f"{'Runner' if m.rol == 'usuario' else 'Tu'}: {m.contenido}" for m in contexto.recientes
        )
        bloques.append(
            "## De lo que veniais hablando\nEsta conversacion ya empezo. NO saludes de "
            "nuevo ni vuelvas a preguntar lo que ya esta aqui.\n" + transcripcion
        )

    bloques.append(base.strip())
    return "\n\n".join(bloques)

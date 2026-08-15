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
from datetime import date, time

from app.application.contexto import (
    ReposDelCoach,
    construir_contexto,
    construir_system_prompt,
    fecha_hablada,
    perfil_hablado,
    plan_hablado,
    sesion_hablada,
)
from app.application.planes import (
    DatosDelPlan,
    consultar_plan_activo,
    consultar_proxima_sesion,
    crear_plan,
)
from app.application.recordatorios import descrito
from app.domain.models import DatosPerfil, Hecho, Runner, TipoRecordatorio
from app.domain.ports.llm_port import (
    EjecutorHerramientas,
    Herramienta,
    LlamadaHerramienta,
    LLMPort,
)
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
        nombre="configurar_recordatorio",
        descripcion=(
            "Cambia la hora de un recordatorio por correo, lo activa o lo desactiva. "
            "Usala cuando el runner diga cosas como 'avisame a las siete' o 'ya no me "
            "mandes correos'. Sin argumentos, te dice como los tiene ahora."
        ),
        esquema={
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["diario", "checkin", "semanal"]},
                "hora": {"type": "integer", "minimum": 0, "maximum": 23},
                "minuto": {"type": "integer", "minimum": 0, "maximum": 59},
                "activo": {"type": "boolean"},
            },
        },
    ),
    Herramienta(
        nombre="registrar_entrenamiento",
        descripcion=(
            "Da por hecha la sesion de un dia y apunta lo que el runner corrio de "
            "verdad. Usala cuando te mande una foto de la pantalla del reloj o te "
            "cuente que ya salio. Lee los numeros de la foto tal cual aparecen: si "
            "alguno no se ve, no lo mandes en vez de adivinarlo."
        ),
        esquema={
            "type": "object",
            "properties": {
                "distancia_km": {"type": "number"},
                "duracion_min": {"type": "number"},
                # Mismo desglose que en crear_plan y por el mismo motivo: un modelo
                # que compone la fecha entera se inventa el anio. Sin dia ni mes, hoy.
                "dia": {"type": "integer", "minimum": 1, "maximum": 31},
                "mes": {"type": "integer", "minimum": 1, "maximum": 12},
                "sensacion": {
                    "type": "string",
                    "description": "Como dijo que se sintio, si lo dijo. Con sus palabras.",
                },
            },
        },
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
        #
        # La FECHA va repetida tres veces a proposito: en la propuesta, en la orden
        # de decirla en voz alta y en los argumentos de la proxima llamada. Sin eso,
        # el modelo proponia "un 21K" a secas, el runner aceptaba, y en el turno
        # siguiente le preguntaba cuando quiere correr — una fecha que le acababan de
        # decir dos frases antes. Entre turno y turno lo unico que sobrevive es lo que
        # Koda dijo en voz alta, asi que un dato que no diga, lo pierde.
        alternativa = no_viable.alternativa
        return (
            f"RECHAZADO: {no_viable} No se ha creado ningun plan. "
            f"Propone al runner un {alternativa.distancia.etiqueta} EL MISMO DIA, "
            f"el {fecha_hablada(fecha_carrera)}: {alternativa.motivo} "
            f"Dile la fecha al proponerselo, no digas solo la distancia. "
            f"Si acepta, llama otra vez a crear_plan con distancia_km "
            f"{alternativa.distancia.km:.0f}, dia {fecha_carrera.day} y mes {fecha_carrera.month}. "
            f"NO le preguntes la fecha otra vez: ya la sabes."
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


async def _configurar_recordatorio(runner: Runner, repos: ReposDelCoach, argumentos: dict) -> str:
    if repos.recordatorios is None:
        return "Los recordatorios no estan disponibles ahora mismo."

    actuales = await repos.recordatorios.de_runner(runner.id)
    if "tipo" not in argumentos:
        if not actuales:
            return "Este runner no tiene ningun recordatorio configurado."
        return "Asi los tiene: " + "; ".join(
            f"{descrito(r)}{'' if r.activo else ' (desactivado)'}" for r in actuales
        )

    try:
        tipo = TipoRecordatorio(str(argumentos["tipo"]))
    except ValueError:
        return "Los tipos validos son diario, checkin y semanal."

    anterior = next((r for r in actuales if r.tipo is tipo), None)
    hora = time(
        hour=int(argumentos.get("hora", anterior.hora_local.hour if anterior else 6)),
        minute=int(argumentos.get("minuto", anterior.hora_local.minute if anterior else 0)),
    )
    activo = bool(argumentos.get("activo", True))
    guardado = await repos.recordatorios.guardar(runner.id, tipo, hora, activo)
    if repos.reprogramar is not None:
        # El cambio no sirve de nada si el aviso ya programado sigue apuntando a la
        # hora vieja: hay que reprogramarlo en caliente.
        await repos.reprogramar(runner)
    if not activo:
        return f"Desactivado: {descrito(guardado)}. Se lo confirmas al runner."
    return f"Guardado: {descrito(guardado)}. Se lo confirmas al runner."


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


async def _registrar_entrenamiento(runner: Runner, repos: ReposDelCoach, argumentos: dict, hoy: date) -> str:
    """Marca la sesion como hecha y guarda lo que se corrio de verdad.

    Los numeros vienen de un modelo leyendo la pantalla de un reloj en una foto, asi
    que NO se usan para recalcular nada del plan: se apuntan como un hecho y se le
    repiten al runner para que los corrija si el modelo leyo mal. El dominio sigue
    calculando solo con la marca que el runner ha confirmado a mano.
    """
    try:
        dia = date(hoy.year, int(argumentos["mes"]), int(argumentos["dia"]))
        # Nadie fotografia el reloj de una carrera que aun no ha hecho: una fecha en
        # el futuro es el modelo equivocandose de mes.
        fecha = dia if dia <= hoy else dia.replace(year=dia.year - 1)
    except (KeyError, TypeError, ValueError):
        fecha = hoy

    hecha = await repos.planes.marcar_completada(runner.id, fecha)

    partes = []
    if (km := argumentos.get("distancia_km")) is not None:
        partes.append(f"{float(km):g} km")
    if (minutos := argumentos.get("duracion_min")) is not None:
        partes.append(f"{float(minutos):g} min")
    if sensacion := argumentos.get("sensacion"):
        partes.append(str(sensacion))
    resumen = ", ".join(partes) if partes else "sin datos"

    if repos.memoria is not None and partes:
        await repos.memoria.guardar(
            runner.id,
            [Hecho(categoria="logro", hecho=f"El {fecha_hablada(fecha)} corrio {resumen}.")],
        )

    if hecha is None:
        return (
            f"Apuntado: {resumen}. Ese dia no le tocaba nada en el plan, asi que no se "
            f"ha marcado ninguna sesion. Repitele los numeros por si leiste mal la foto."
        )
    return (
        f"Marcada como hecha la sesion del {fecha_hablada(fecha)} ({sesion_hablada(hecha)}). "
        f"Registrado: {resumen}. Repitele los numeros al runner por si leiste mal la "
        f"pantalla, y comenta que tal le queda respecto a lo que tocaba."
    )


# --- El puente entre la voz y el cerebro -----------------------------------------
#
# Ver docs/adr/ADR-020-nova-habla-y-sonnet-decide.md.
#
# En voz, Nova Sonic NO recibe estas cinco herramientas: recibe solo la de abajo, y
# el contexto del runner tampoco. Todo lo que sabe Koda vive detras de esta llamada.
#
# Es la misma idea que ya sostiene el resto del proyecto: en vez de pedirle a un
# modelo que no invente, se le quita aquello con lo que podria inventar. Un modelo
# que no tiene el ritmo del runner en el contexto no puede decir un ritmo equivocado
# — como mucho puede callarse.

NOMBRE_HERRAMIENTA_PUENTE = "preguntar_al_entrenador"

HERRAMIENTAS_VOZ: tuple[Herramienta, ...] = (
    Herramienta(
        nombre=NOMBRE_HERRAMIENTA_PUENTE,
        descripcion=(
            "El entrenador. Sabe quien es el runner, que plan tiene, sus ritmos y todo lo "
            "que han hablado antes. Llamalo SIEMPRE, con cualquier cosa que diga el runner "
            "— un saludo, una pregunta, un simple 'si'. Tu no sabes nada; el si. Pasale lo "
            "que dijo tal cual y despues di en voz alta lo que te devuelva."
        ),
        esquema={
            "type": "object",
            "properties": {
                "peticion": {
                    "type": "string",
                    "description": "Lo que acaba de decir el runner, literal y sin resumir.",
                }
            },
            "required": ["peticion"],
        },
    ),
)

_ENTRENADOR_NO_DISPONIBLE = (
    "No he podido consultar al entrenador ahora mismo. Dile que lo intente en un momento "
    "y NO te inventes ninguna respuesta."
)


def ejecutor_de_voz(
    runner: Runner,
    repos: ReposDelCoach,
    *,
    llm: LLMPort,
    system_prompt: str,
    hoy: date | None = None,
) -> EjecutorHerramientas:
    """El ejecutor que ve Nova Sonic: una sola herramienta, que por dentro es una
    conversacion entera con el modelo grande.

    El contexto se arma AQUI, en cada llamada, y no al abrir la sesion: dentro de un
    mismo turno el runner puede guardar su perfil y pedir un plan seguido, y el
    segundo tiene que ver lo que guardo el primero.
    """
    dia = hoy or date.today()
    herramientas_de_verdad = ejecutor_para(runner, repos, dia)

    async def ejecutar(llamada: LlamadaHerramienta) -> str:
        if llamada.nombre != NOMBRE_HERRAMIENTA_PUENTE:
            # No deberia pasar: es la unica que se le ofrece. Si pasa, se dice — un
            # locutor sin respuesta se calla, no improvisa.
            logger.warning("La voz pidio una herramienta que no tiene: %s", llamada.nombre)
            return _ENTRENADOR_NO_DISPONIBLE

        peticion = str(llamada.argumentos.get("peticion", "")).strip()
        if not peticion:
            return _ENTRENADOR_NO_DISPONIBLE

        actual = await repos.runners.obtener(runner.id) or runner
        contexto = await construir_contexto(actual, repos, dia)
        try:
            respuesta = await llm.conversar(
                peticion,
                system_prompt=construir_system_prompt(system_prompt, contexto),
                herramientas=HERRAMIENTAS,
                ejecutar=herramientas_de_verdad,
            )
        except Exception:  # noqa: BLE001 — el gateway ya agoto sus proveedores
            logger.warning("El entrenador no contesto a una consulta de voz", exc_info=True)
            return _ENTRENADOR_NO_DISPONIBLE

        logger.info("Entrenador -> %d caracteres para la voz", len(respuesta))
        return respuesta or _ENTRENADOR_NO_DISPONIBLE

    return ejecutar


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
        if llamada.nombre == "configurar_recordatorio":
            return await _configurar_recordatorio(actual, repos, llamada.argumentos)
        if llamada.nombre == "registrar_entrenamiento":
            return await _registrar_entrenamiento(actual, repos, llamada.argumentos, dia)
        return f"No existe ninguna herramienta llamada {llamada.nombre}."

    return ejecutar

"""Los tres correos y a quién se le mandan.

Regla que manda aquí: **un correo que no dice nada no se manda**. Un recordatorio
diario que repite "hoy descansa" siete veces enseña al runner a ignorarlos, y a partir
de ahí el canal está muerto aunque el día que importe tengas algo bueno que decir.
Todas las funciones de redacción devuelven None cuando no hay nada que contar.

El contenido sale del plan real, nunca de un LLM: si el correo dijera algo distinto de
lo que dice la app, el runner no sabría a cuál creer.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.application.contexto import ReposDelCoach, sesion_hablada
from app.domain.models import Recordatorio, Runner, TipoRecordatorio
from app.domain.ports.email_port import EmailPort
from app.domain.ports.repositories import RecordatorioRepo
from app.domain.training.modelos import PlanActivo, SesionProgramada

# Horas por defecto al darse de alta. El runner las cambia desde su perfil o hablando.
HORAS_POR_DEFECTO = {
    TipoRecordatorio.DIARIO: 6,
    TipoRecordatorio.CHECKIN: 20,
    TipoRecordatorio.SEMANAL: 19,
}
DIA_DEL_SEMANAL = 6  # domingo: se mira la semana que termina y la que entra


@dataclass(frozen=True)
class ContenidoCorreo:
    asunto: str
    parrafos: tuple[str, ...]


def _sesiones_del_dia(plan: PlanActivo, dia: date) -> list[SesionProgramada]:
    return [s for s in plan.sesiones_programadas() if s.fecha == dia]


def redactar_diario(runner: Runner, plan: PlanActivo | None, hoy: date) -> ContenidoCorreo | None:
    """Qué te toca hoy. No se manda si hoy no hay sesión: el descanso no es noticia."""
    if plan is None:
        return None
    sesiones = _sesiones_del_dia(plan, hoy)
    if not sesiones:
        return None

    nombre = f"{runner.nombre}, " if runner.nombre else ""
    parrafos = [f"{nombre}esto es lo que toca hoy:"]
    parrafos += [s.sesion.descripcion for s in sesiones]

    dias_para_la_carrera = (plan.objetivo.fecha_carrera - hoy).days
    if 0 < dias_para_la_carrera <= 21:
        parrafos.append(f"Quedan {dias_para_la_carrera} días para tu {plan.objetivo.distancia.etiqueta}.")
    return ContenidoCorreo(
        asunto=f"Hoy: {sesiones[0].sesion.descripcion[:60]}",
        parrafos=tuple(parrafos),
    )


def redactar_checkin(runner: Runner, plan: PlanActivo | None, hoy: date) -> ContenidoCorreo | None:
    """¿Saliste? Solo tiene sentido si hoy había algo que hacer."""
    if plan is None or not _sesiones_del_dia(plan, hoy):
        return None
    return ContenidoCorreo(
        asunto="¿Cómo fue hoy?",
        parrafos=(
            "¿Saliste a correr?",
            "Cuéntamelo en la app y ajusto lo que venga. Si no pudiste, tampoco pasa nada: "
            "una sesión no hace ni deshace un plan.",
        ),
    )


def redactar_semanal(runner: Runner, plan: PlanActivo | None, hoy: date) -> ContenidoCorreo | None:
    """Resumen de la semana que termina y aviso de la que entra."""
    if plan is None:
        return None

    programadas = plan.sesiones_programadas()
    entrante = [s for s in programadas if 0 < (s.fecha - hoy).days <= 7]
    if not entrante:
        return None

    kilometros = round(sum(s.sesion.distancia_km for s in entrante), 1)
    semana = entrante[0].semana
    parrafos = [
        f"La semana que viene es la {semana} de {len(plan.plan.semanas)} de tu "
        f"{plan.objetivo.distancia.etiqueta}: {kilometros} km repartidos así.",
    ]
    parrafos += [sesion_hablada(s) for s in entrante]

    la_semana = next((s for s in plan.plan.semanas if s.numero == semana), None)
    if la_semana is not None and la_semana.es_descarga:
        parrafos.append("Es semana de descarga: baja el volumen a propósito, para asimilar. No la saltes.")
    elif la_semana is not None and la_semana.es_taper:
        parrafos.append("Estás en taper: menos volumen, misma intensidad. Llegar fresco es parte del plan.")
    return ContenidoCorreo(asunto=f"Tu semana {semana}: {kilometros} km", parrafos=tuple(parrafos))


_REDACTORES = {
    TipoRecordatorio.DIARIO: redactar_diario,
    TipoRecordatorio.CHECKIN: redactar_checkin,
    TipoRecordatorio.SEMANAL: redactar_semanal,
}


async def enviar_recordatorio(
    *,
    runner_id: UUID,
    tipo: TipoRecordatorio,
    repos: ReposDelCoach,
    recordatorios: RecordatorioRepo,
    email: EmailPort,
    plantilla_html: str,
    url_baja: str,
    url_app: str,
    hoy: date | None = None,
) -> bool:
    """Redacta y envía UN recordatorio a UN runner. Devuelve si se llegó a mandar.

    Recibe runner_id y vuelve a cargar los datos acotados por él. Nunca se le pasa un
    runner ya cargado desde fuera: el job del scheduler solo conoce un identificador, y
    todo lo demás se busca aquí — ver 03-MULTIUSUARIO-Y-SEGURIDAD.md §4.5.
    """
    dia = hoy or date.today()
    runner = await repos.runners.obtener(runner_id)
    if runner is None or not runner.activo:
        return False

    plan = await repos.planes.obtener_activo(runner_id)
    contenido = _REDACTORES[tipo](runner, plan, dia)
    if contenido is None:
        return False

    texto = "\n\n".join(contenido.parrafos) + f"\n\n---\nDejar de recibir estos correos: {url_baja}"
    html = renderizar_html(plantilla_html, contenido, url_baja, url_app)
    await email.enviar(runner.email, contenido.asunto, texto, html)
    await recordatorios.marcar_enviado(runner_id, tipo, datetime.now(UTC))
    return True


def renderizar_html(plantilla: str, contenido: ContenidoCorreo, url_baja: str, url_app: str) -> str:
    cuerpo = "\n".join(f"<p>{_escapar(p)}</p>" for p in contenido.parrafos)
    return (
        plantilla.replace("{{titulo}}", _escapar(contenido.asunto))
        .replace("{{cuerpo}}", cuerpo)
        .replace("{{url_baja}}", _escapar(url_baja))
        .replace("{{url_app}}", _escapar(url_app))
    )


def _escapar(texto: str) -> str:
    """El contenido lleva el nombre del runner y descripciones de sesiones. Nada de eso
    deberia traer HTML, y precisamente por eso no se confia en que no lo traiga."""
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def descrito(recordatorio: Recordatorio) -> str:
    """Como se le cuenta al runner cuando pregunta por sus avisos."""
    cuando = recordatorio.hora_local.strftime("%H:%M")
    if recordatorio.tipo is TipoRecordatorio.SEMANAL:
        return f"resumen semanal, domingos a las {cuando}"
    if recordatorio.tipo is TipoRecordatorio.DIARIO:
        return f"sesion del dia, todos los dias a las {cuando}"
    return f"check-in de la noche, todos los dias a las {cuando}"

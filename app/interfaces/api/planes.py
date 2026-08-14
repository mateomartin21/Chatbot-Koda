"""Plan de entrenamiento y perfil del runner.

Como en el resto de la API, runner_id sale SIEMPRE de get_current_runner(): ninguna
ruta de aqui acepta un identificador de usuario en el cuerpo ni en la query. Ver
docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §4.2.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.application.planes import (
    DatosDelPlan,
    actualizar_perfil,
    consultar_plan_activo,
    consultar_proxima_sesion,
    crear_plan,
)
from app.domain.models import DatosPerfil, Runner
from app.domain.training.modelos import PlanActivo, PlanNoViable, SesionProgramada, ValorInvalido
from app.domain.training.paces import Ritmo, ZonasRitmo
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos
from app.interfaces.api.deps import (
    Repos,
    get_current_runner,
    get_repos,
    get_scheduler,
)
from app.interfaces.avisos import programar_para

router = APIRouter(prefix="/api", tags=["planes"])


# --- Esquemas de respuesta ------------------------------------------------------


class SesionRespuesta(BaseModel):
    dia_semana: int
    fecha: date
    tipo: str
    distancia_km: float
    descripcion: str
    ritmo_objetivo: str | None
    completada: bool


class SemanaRespuesta(BaseModel):
    numero: int
    volumen_km: float
    es_descarga: bool
    es_taper: bool
    sesiones: list[SesionRespuesta]


class PlanRespuesta(BaseModel):
    distancia: str
    fecha_carrera: date
    nombre_carrera: str | None
    fecha_inicio: date
    semanas: list[SemanaRespuesta]
    zonas: dict[str, str]
    ritmos_estimados: bool
    notas: list[str]
    volumen_total_km: float
    proxima_sesion: SesionRespuesta | None


class PerfilRespuesta(BaseModel):
    email: str
    nombre: str | None
    edad: int | None
    nivel: str | None
    dias_disponibles: int | None
    zona_horaria: str | None
    marca_distancia_km: float | None
    marca_tiempo_seg: float | None


class PerfilPeticion(BaseModel):
    nombre: str | None = None
    # La manda el navegador solo: nadie deberia elegir su huso en un desplegable
    # cuando el aparato ya lo sabe. De aqui sale la hora a la que llegan los avisos.
    zona_horaria: str | None = Field(None, max_length=64)
    edad: int | None = Field(None, ge=10, le=100)
    nivel: str | None = None
    dias_disponibles: int | None = Field(None, ge=2, le=7)
    marca_distancia_km: float | None = Field(None, gt=0, le=100)
    marca_tiempo_seg: float | None = Field(None, gt=0)


class PlanPeticion(BaseModel):
    distancia_km: float
    fecha_carrera: date
    dias_por_semana: int | None = Field(None, ge=2, le=7)
    nombre_carrera: str | None = None
    tiempo_meta_seg: float | None = Field(None, gt=0)


def _zonas_legibles(zonas: ZonasRitmo) -> dict[str, str]:
    return {
        "facil": str(zonas.facil),
        "larga": str(zonas.larga),
        "tempo": str(zonas.tempo),
        "intervalos": str(zonas.intervalos),
        "objetivo": str(zonas.objetivo),
    }


def _ritmo_legible(seg_por_km: float | None) -> str | None:
    # El ritmo viaja a la interfaz ya formateado ("5:42/km"): que cada cliente lo
    # formatee por su cuenta es como acaban divergiendo la web y el correo.
    return str(Ritmo(seg_por_km)) if seg_por_km else None


def _sesion_a_respuesta(programada: SesionProgramada) -> SesionRespuesta:
    sesion = programada.sesion
    return SesionRespuesta(
        dia_semana=sesion.dia_semana,
        fecha=programada.fecha,
        tipo=sesion.tipo.value,
        distancia_km=sesion.distancia_km,
        descripcion=sesion.descripcion,
        ritmo_objetivo=_ritmo_legible(sesion.ritmo_objetivo_seg_km),
        completada=programada.completada,
    )


def _plan_a_respuesta(activo: PlanActivo, proxima: SesionProgramada | None) -> PlanRespuesta:
    programadas = activo.sesiones_programadas(incluir_descansos=True)
    por_semana = {semana.numero: semana for semana in activo.plan.semanas}
    semanas = [
        SemanaRespuesta(
            numero=numero,
            volumen_km=round(por_semana[numero].volumen_km, 1),
            es_descarga=por_semana[numero].es_descarga,
            es_taper=por_semana[numero].es_taper,
            sesiones=[_sesion_a_respuesta(p) for p in programadas if p.semana == numero],
        )
        for numero in sorted(por_semana)
    ]
    return PlanRespuesta(
        distancia=activo.objetivo.distancia.etiqueta,
        fecha_carrera=activo.objetivo.fecha_carrera,
        nombre_carrera=activo.objetivo.nombre_carrera,
        fecha_inicio=activo.fecha_inicio,
        semanas=semanas,
        zonas=_zonas_legibles(activo.plan.zonas),
        ritmos_estimados=activo.plan.ritmos_estimados,
        notas=list(activo.plan.notas),
        volumen_total_km=round(activo.plan.volumen_total_km, 1),
        proxima_sesion=_sesion_a_respuesta(proxima) if proxima else None,
    )


# --- Rutas ----------------------------------------------------------------------


@router.get("/perfil", response_model=PerfilRespuesta)
async def ver_perfil(runner: Runner = Depends(get_current_runner)) -> PerfilRespuesta:
    return PerfilRespuesta(
        email=runner.email,
        nombre=runner.nombre,
        edad=runner.edad,
        nivel=runner.nivel,
        dias_disponibles=runner.dias_disponibles,
        zona_horaria=runner.zona_horaria,
        marca_distancia_km=runner.marca_distancia_km,
        marca_tiempo_seg=runner.marca_tiempo_seg,
    )


@router.put("/perfil", response_model=PerfilRespuesta)
async def guardar_perfil(
    peticion: PerfilPeticion,
    runner: Runner = Depends(get_current_runner),
    repos: Repos = Depends(get_repos),
    scheduler: APSchedulerAvisos = Depends(get_scheduler),
) -> PerfilRespuesta:
    actualizado = await actualizar_perfil(runner, DatosPerfil(**peticion.model_dump()), repos.runners)
    if peticion.zona_horaria and peticion.zona_horaria != runner.zona_horaria:
        # Se movio de huso (o lo dijo por primera vez): los avisos ya programados
        # apuntan a la hora vieja y hay que recalcularlos.
        await programar_para(actualizado, repos.recordatorios, scheduler)
    return await ver_perfil(actualizado)


@router.get("/plan", response_model=PlanRespuesta | None)
async def ver_plan(
    runner: Runner = Depends(get_current_runner),
    repos: Repos = Depends(get_repos),
) -> PlanRespuesta | None:
    activo = await consultar_plan_activo(runner.id, repos.planes)
    if activo is None:
        return None
    proxima = await consultar_proxima_sesion(runner.id, repos.planes)
    return _plan_a_respuesta(activo, proxima)


@router.post("/plan", response_model=PlanRespuesta, status_code=201)
async def generar_plan(
    peticion: PlanPeticion,
    runner: Runner = Depends(get_current_runner),
    repos: Repos = Depends(get_repos),
) -> PlanRespuesta:
    try:
        activo = await crear_plan(
            runner=runner,
            datos=DatosDelPlan(**peticion.model_dump()),
            runners=repos.runners,
            planes=repos.planes,
        )
    except PlanNoViable as no_viable:
        # 409 y no 400: la peticion esta bien formada, lo que no encaja es la realidad.
        # El cuerpo lleva la alternativa concreta — un rechazo sin salida es solo un no.
        raise HTTPException(
            409,
            detail={
                "mensaje": str(no_viable),
                "alternativa": {
                    "distancia": no_viable.alternativa.distancia.etiqueta,
                    "distancia_km": no_viable.alternativa.distancia.km,
                    "motivo": no_viable.alternativa.motivo,
                    "semanas_disponibles": no_viable.alternativa.semanas_disponibles,
                },
            },
        ) from None
    except ValorInvalido as invalido:
        raise HTTPException(400, str(invalido)) from None

    proxima = await consultar_proxima_sesion(runner.id, repos.planes)
    return _plan_a_respuesta(activo, proxima)

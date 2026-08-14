"""Recordatorios: consultarlos, cambiarlos y darse de baja.

La baja NO exige iniciar sesión — va por un enlace firmado que viaja en el propio
correo. Obligar a entrar para dejar de recibir correos es de las cosas que hacen que la
gente marque como spam en vez de darse de baja, y eso destroza la reputación de envío.
"""

import logging
from datetime import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.application.recordatorios import descrito
from app.config import Settings
from app.domain.models import Runner, TipoRecordatorio
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos
from app.interfaces.api.deps import (
    Repos,
    get_current_runner,
    get_repos,
    get_scheduler,
    get_settings,
)
from app.interfaces.avisos import programar_para, runner_de_token_baja

router = APIRouter(prefix="/api/recordatorios", tags=["recordatorios"])
logger = logging.getLogger(__name__)

_PAGINA_DE_BAJA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8" /><title>Koda</title></head>
<body style="font-family:system-ui,sans-serif;max-width:420px;margin:80px auto;
padding:0 24px;text-align:center;color:#18181b;">
<h1 style="font-size:20px;">Listo, no te escribimos más</h1>
<p style="color:#52525b;line-height:1.5;">{mensaje}</p>
<p><a href="{url_app}" style="color:#ff6a3d;">Volver a Koda</a></p>
</body></html>"""


class RecordatorioRespuesta(BaseModel):
    tipo: str
    hora_local: str
    activo: bool
    descripcion: str


class RecordatorioPeticion(BaseModel):
    tipo: str
    hora_local: str = Field(pattern=r"^\d{1,2}:\d{2}$", description="HH:MM en la hora del runner")
    activo: bool = True


def _a_respuesta(recordatorio) -> RecordatorioRespuesta:
    return RecordatorioRespuesta(
        tipo=recordatorio.tipo.value,
        hora_local=recordatorio.hora_local.strftime("%H:%M"),
        activo=recordatorio.activo,
        descripcion=descrito(recordatorio),
    )


@router.get("", response_model=list[RecordatorioRespuesta])
async def ver_recordatorios(
    runner: Runner = Depends(get_current_runner),
    repos: Repos = Depends(get_repos),
) -> list[RecordatorioRespuesta]:
    return [_a_respuesta(r) for r in await repos.recordatorios.de_runner(runner.id)]


@router.put("", response_model=list[RecordatorioRespuesta])
async def guardar_recordatorio(
    peticion: RecordatorioPeticion,
    runner: Runner = Depends(get_current_runner),
    repos: Repos = Depends(get_repos),
    scheduler: APSchedulerAvisos = Depends(get_scheduler),
) -> list[RecordatorioRespuesta]:
    try:
        tipo = TipoRecordatorio(peticion.tipo)
        horas, minutos = (int(p) for p in peticion.hora_local.split(":"))
        hora = time(hour=horas, minute=minutos)
    except ValueError as invalido:
        raise HTTPException(400, str(invalido)) from None

    await repos.recordatorios.guardar(runner.id, tipo, hora, peticion.activo)
    # Reprogramar en caliente: si solo se guardara en la tabla, el cambio no tendria
    # efecto hasta el siguiente reinicio y el runner seguiria recibiendo a la hora vieja.
    await programar_para(runner, repos.recordatorios, scheduler)
    return [_a_respuesta(r) for r in await repos.recordatorios.de_runner(runner.id)]


@router.get("/baja")
async def darse_de_baja(
    token: str,
    repos: Repos = Depends(get_repos),
    settings: Settings = Depends(get_settings),
    scheduler: APSchedulerAvisos = Depends(get_scheduler),
) -> Response:
    try:
        runner_id = runner_de_token_baja(token, settings)
    except jwt.PyJWTError:
        raise HTTPException(404) from None  # 404 y no 403: no se confirma que exista

    desactivados = await repos.recordatorios.desactivar_todos(runner_id)
    scheduler.cancelar_todos(runner_id)
    logger.info("Baja de recordatorios de %s (%d desactivados)", runner_id, desactivados)

    mensaje = (
        "Ya no vas a recibir recordatorios. Puedes volver a activarlos cuando quieras "
        "desde tu perfil, o pidiéndomelo hablando."
    )
    return Response(
        content=_PAGINA_DE_BAJA.format(mensaje=mensaje, url_app=settings.app_base_url),
        media_type="text/html",
    )

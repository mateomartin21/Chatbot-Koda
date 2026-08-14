"""POST /api/auth/solicitar · GET /api/auth/canjear — ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §3."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.application.auth.canjear_enlace import canjear_enlace
from app.application.auth.solicitar_enlace import solicitar_enlace
from app.config import Settings
from app.domain.models import Runner
from app.domain.ports.email_port import EmailPort
from app.infrastructure.scheduler.apscheduler_adapter import APSchedulerAvisos
from app.interfaces.api.deps import (
    COOKIE_NAME,
    Repos,
    crear_jwt,
    get_current_runner,
    get_email_port,
    get_repos,
    get_scheduler,
    get_settings,
)
from app.interfaces.avisos import alta_por_defecto, programar_para

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SolicitarEnlaceRequest(BaseModel):
    email: EmailStr


@router.post("/solicitar")
async def solicitar(
    payload: SolicitarEnlaceRequest,
    request: Request,
    repos: Repos = Depends(get_repos),
    email_port: EmailPort = Depends(get_email_port),
    settings: Settings = Depends(get_settings),
) -> dict:
    ip = request.client.host if request.client else None
    await solicitar_enlace(
        str(payload.email),
        ip,
        runners=repos.runners,
        tokens=repos.tokens,
        email_port=email_port,
        settings=settings,
    )
    # Siempre 200: no se revela si el correo existe ni si se toco el rate limit.
    return {"ok": True}


@router.get("/canjear")
async def canjear(
    token: str,
    repos: Repos = Depends(get_repos),
    settings: Settings = Depends(get_settings),
    scheduler: APSchedulerAvisos = Depends(get_scheduler),
) -> Response:
    runner = await canjear_enlace(token, tokens=repos.tokens, runners=repos.runners)
    if runner is None:
        raise HTTPException(401, "Enlace invalido o caducado")

    # Los recordatorios son opt-out, no opt-in: uno que hay que activar a mano no lo
    # activa casi nadie, y son el punto extra del enunciado. Si ya los tenia (aunque
    # estuvieran dados de baja) no se le tocan — darse de baja tiene que ser definitivo.
    await alta_por_defecto(runner.id, repos.recordatorios)
    await programar_para(runner, repos.recordatorios, scheduler)

    response = RedirectResponse(url="/", status_code=307)
    response.set_cookie(
        key=COOKIE_NAME,
        value=crear_jwt(runner.id, settings),
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=60 * 60 * 24 * settings.jwt_expire_days,
        path="/",
    )
    return response


@router.get("/sesion")
async def sesion(runner: Runner = Depends(get_current_runner)) -> dict:
    # La cookie es httpOnly a proposito (mitiga XSS) — el frontend no puede leerla,
    # asi que pregunta aqui si hay sesion valida en vez de inspeccionar document.cookie.
    return {"email": runner.email}

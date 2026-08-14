import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.interfaces.api import auth, health, mensajes, planes, recordatorios, voz_ws
from app.interfaces.api.deps import get_container, get_scheduler
from app.interfaces.avisos import reprogramar_todo

# settings.log_level existia en config.py pero nada lo aplicaba -- sin esto, logger.info()
# en cualquier modulo (ej. voz_ws.py) se pierde en silencio, solo WARNING+ se ve por
# defecto en Python.
logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Los avisos programados se reconstruyen al arrancar leyendo la tabla
    `recordatorios`, que es su unica fuente de verdad — docs/adr/ADR-014-jobs-en-memoria.md.

    Si la base no responde, la app arranca igual y sin recordatorios: quedarse sin
    correos es molesto, no poder entrar a hablar con el coach es descalificante.
    """
    scheduler = get_scheduler()
    scheduler.iniciar()
    try:
        await reprogramar_todo(get_container(), scheduler)
    except Exception:  # noqa: BLE001
        logger.warning("No se pudieron reprogramar los avisos al arrancar", exc_info=True)
    yield
    scheduler.detener()


app = FastAPI(title="Koda Running Coach", lifespan=ciclo_de_vida)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(mensajes.router)
app.include_router(planes.router)
app.include_router(recordatorios.router)
app.include_router(voz_ws.router)

WEB_DIR = Path(__file__).parent / "interfaces" / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

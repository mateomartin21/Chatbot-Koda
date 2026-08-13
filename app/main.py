import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.interfaces.api import auth, health, mensajes, voz_ws

# settings.log_level existia en config.py pero nada lo aplicaba -- sin esto, logger.info()
# en cualquier modulo (ej. voz_ws.py) se pierde en silencio, solo WARNING+ se ve por
# defecto en Python.
logging.basicConfig(level=get_settings().log_level)

app = FastAPI(title="Koda Running Coach")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(mensajes.router)
app.include_router(voz_ws.router)

WEB_DIR = Path(__file__).parent / "interfaces" / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

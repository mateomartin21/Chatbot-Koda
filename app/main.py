from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.interfaces.api import auth, health

app = FastAPI(title="Koda Running Coach")

app.include_router(health.router)
app.include_router(auth.router)

WEB_DIR = Path(__file__).parent / "interfaces" / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

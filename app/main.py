import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.config import get_settings
from app.interfaces.api import auth, health, mensajes, planes, recordatorios, voz_ws
from app.interfaces.api.deps import get_container, get_scheduler
from app.interfaces.avisos import reprogramar_todo

# settings.log_level existia en config.py pero nada lo aplicaba -- sin esto, logger.info()
# en cualquier modulo (ej. voz_ws.py) se pierde en silencio, solo WARNING+ se ve por
# defecto en Python.
logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


def _ajustes_que_faltan(settings: Any) -> list[str]:
    """Los ajustes sin los que el proveedor elegido no puede funcionar.

    Antes esto lo comprobaba cada adaptador en su constructor, y tenia un efecto que
    nadie habia mirado: como el contenedor se arma al importar `deps`, **la aplicacion
    entera dejaba de poder importarse** sin una cuenta de AWS configurada. La suite de
    tests incluida — que se supone que corre sin credenciales — solo pasaba porque la
    maquina de quien la ejecutaba tenia un `.env` al lado. En CI, que no lo tiene,
    llevaba fallando desde el primer dia.

    Comprobarlo aqui conserva lo bueno de aquello (enterarse pronto, no en la primera
    peticion) y quita lo malo: importar un modulo no exige tener la nube configurada.
    """
    faltan = []
    if settings.provider_stt == "aws" and not settings.s3_bucket:
        faltan.append("S3_BUCKET (lo necesita Transcribe para dejar el audio)")
    if settings.provider_stt != "aws" and not settings.groq_api_key:
        faltan.append("GROQ_API_KEY (PROVIDER_STT no es 'aws')")
    if not settings.bedrock_model_id:
        faltan.append("BEDROCK_MODEL_ID (sin el no hay modelo principal)")
    if settings.provider_email == "aws" and not settings.ses_from_email:
        faltan.append("SES_FROM_EMAIL (sin el no salen los enlaces magicos)")
    return faltan


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Los avisos programados se reconstruyen al arrancar leyendo la tabla
    `recordatorios`, que es su unica fuente de verdad — docs/adr/ADR-014-jobs-en-memoria.md.

    Si la base no responde, la app arranca igual y sin recordatorios: quedarse sin
    correos es molesto, no poder entrar a hablar con el coach es descalificante.
    """
    ajustes = get_settings()
    if faltan := _ajustes_que_faltan(ajustes):
        aviso = "Configuracion incompleta: " + "; ".join(faltan)
        # En produccion es preferible no arrancar: un servidor vivo que no puede
        # mandar un correo ni contestar un mensaje se parece demasiado a uno sano.
        # En desarrollo se avisa y se sigue: media aplicacion es suficiente para
        # trabajar en la otra media.
        if ajustes.app_env == "production":
            raise RuntimeError(aviso)
        logger.warning(aviso)

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


class Estaticos(StaticFiles):
    """StaticFiles con una politica de cache explicita.

    Sin `Cache-Control`, el navegador aplica su heuristica: guarda el fichero
    durante un 10% del tiempo que lleva sin modificarse. Un `app.js` tocado hace
    tres dias se queda cacheado unas siete horas, y en ese rato lo que se despliega
    y lo que se ve dejan de ser lo mismo — con la pinta de un bug del servidor.

    `no-cache` no significa "no lo guardes": significa "guardalo, pero preguntame
    antes de usarlo". Como StaticFiles ya manda ETag, la pregunta se contesta con un
    304 vacio si no ha cambiado. El coste es un viaje de ida y vuelta; lo que se
    compra es que un despliegue se vea al recargar, siempre.

    Las tipografias son la excepcion: su nombre no cambia nunca porque su contenido
    tampoco, y son lo mas pesado que se sirve.
    """

    INMUTABLES = frozenset({".woff2", ".woff", ".ttf"})

    def file_response(self, full_path: str, *args: Any, **kwargs: Any) -> Response:
        respuesta = super().file_response(full_path, *args, **kwargs)
        if Path(full_path).suffix.lower() in self.INMUTABLES:
            respuesta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


WEB_DIR = Path(__file__).parent / "interfaces" / "web"
app.mount("/", Estaticos(directory=WEB_DIR, html=True), name="web")

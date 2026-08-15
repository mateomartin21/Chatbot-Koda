# Koda en un contenedor.
#
# Dos etapas: la primera compila las ruedas de las dependencias, la segunda solo
# las instala. Sin separar, la imagen final se lleva gcc y las cabeceras de
# desarrollo — unos 300 MB de herramientas que en produccion no ejecuta nadie y que
# solo sirven para ampliar la superficie de ataque.
#
# 3.13 y no 3.14: es la ultima version con ruedas precompiladas para todo lo que hay
# en requirements.txt. Con 3.14, asyncpg y Pillow se compilan desde fuente y la
# imagen tarda diez minutos en construirse.

FROM python:3.13-slim AS ruedas

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ruedas
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /ruedas/dist -r requirements.txt


FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# La aplicacion no corre como root. Si alguien encontrara una forma de ejecutar algo
# dentro del contenedor, lo hace como un usuario sin permisos sobre nada.
RUN useradd --create-home --uid 10001 koda

WORKDIR /app

COPY --from=ruedas /ruedas/dist /ruedas/dist
COPY requirements.txt .
RUN pip install --no-index --find-links=/ruedas/dist -r requirements.txt \
    && rm -rf /ruedas

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER koda

EXPOSE 8000

# Un solo worker a proposito. Los recordatorios los agenda APScheduler EN MEMORIA
# (docs/adr/ADR-014-jobs-en-memoria.md): con dos workers, cada uno reconstruye la
# misma agenda al arrancar y el runner recibe cada correo por duplicado.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

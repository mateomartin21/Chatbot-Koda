"""Construye clientes boto3 con credenciales explicitas desde Settings.

pydantic-settings carga .env dentro del objeto Settings, pero NO lo exporta como
variables de entorno del proceso (a diferencia de python-dotenv.load_dotenv()).
boto3.client(...) sin credenciales explicitas depende de esas variables de entorno
para su chain de credenciales por defecto, asi que sin este helper cualquier
adaptador AWS lanzaba NoCredentialsError fuera de scripts que sí llaman load_dotenv().

Pasar None es seguro cuando no aplica (ej. un IAM role en EC2/Lambda mas adelante):
boto3 sigue resolviendo por su chain por defecto en ese caso.
"""

import os

import boto3

from app.config import Settings


def cliente_aws(servicio: str, settings: Settings):
    return boto3.client(
        servicio,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def exportar_credenciales_a_entorno(settings: Settings) -> None:
    """Nova Sonic no usa boto3 — usa aws_sdk_bedrock_runtime + smithy_aws_core, un SDK
    async aparte que resuelve credenciales SOLO por variables de entorno
    (EnvironmentCredentialsResolver), no por parametros explicitos. Es el mismo problema
    que cliente_aws() ya resuelve para boto3, pero aqui no hay forma de pasar las
    credenciales directas — hay que exportarlas. setdefault() para no pisar variables
    que el entorno ya pudiera traer (ej. un IAM role futuro)."""
    if settings.aws_access_key_id:
        os.environ.setdefault("AWS_ACCESS_KEY_ID", settings.aws_access_key_id)
    if settings.aws_secret_access_key:
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", settings.aws_secret_access_key)
    os.environ.setdefault("AWS_DEFAULT_REGION", settings.aws_region)

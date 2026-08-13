"""Construye clientes boto3 con credenciales explicitas desde Settings.

pydantic-settings carga .env dentro del objeto Settings, pero NO lo exporta como
variables de entorno del proceso (a diferencia de python-dotenv.load_dotenv()).
boto3.client(...) sin credenciales explicitas depende de esas variables de entorno
para su chain de credenciales por defecto, asi que sin este helper cualquier
adaptador AWS lanzaba NoCredentialsError fuera de scripts que sí llaman load_dotenv().

Pasar None es seguro cuando no aplica (ej. un IAM role en EC2/Lambda mas adelante):
boto3 sigue resolviendo por su chain por defecto en ese caso.
"""

import boto3

from app.config import Settings


def cliente_aws(servicio: str, settings: Settings):
    return boto3.client(
        servicio,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

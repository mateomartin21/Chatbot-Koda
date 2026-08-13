"""Adaptador de EmailPort sobre Amazon SES v2."""

import asyncio

import boto3

from app.config import Settings
from app.domain.ports.email_port import EmailPort


class SESEmail(EmailPort):
    def __init__(self, settings: Settings) -> None:
        self._client = boto3.client("sesv2", region_name=settings.aws_region)
        self._from_email = settings.ses_from_email
        self._from_name = settings.ses_from_name

    async def enviar(self, destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
        body: dict = {"Text": {"Data": texto}}
        if html is not None:
            body["Html"] = {"Data": html}
        # boto3 es sincrono/bloqueante — se saca del event loop, ver docs/contexto/08-CONVENCIONES.md
        await asyncio.to_thread(
            self._client.send_email,
            FromEmailAddress=f"{self._from_name} <{self._from_email}>",
            Destination={"ToAddresses": [destinatario]},
            Content={"Simple": {"Subject": {"Data": asunto}, "Body": body}},
        )

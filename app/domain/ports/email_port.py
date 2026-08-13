"""Puerto de envio de correo. La implementacion concreta (SES, Resend...) vive en infrastructure/."""

from abc import ABC, abstractmethod


class EmailPort(ABC):
    @abstractmethod
    async def enviar(self, destinatario: str, asunto: str, texto: str, html: str | None = None) -> None: ...

from dataclasses import dataclass

from app.domain.ports.email_port import EmailPort


@dataclass
class CorreoEnviado:
    destinatario: str
    asunto: str
    texto: str
    html: str | None = None


class FakeEmail(EmailPort):
    def __init__(self) -> None:
        self.enviados: list[CorreoEnviado] = []

    async def enviar(self, destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
        self.enviados.append(CorreoEnviado(destinatario, asunto, texto, html))

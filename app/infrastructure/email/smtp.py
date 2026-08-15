"""Adaptador de EmailPort sobre SMTP.

Existe por una razon muy concreta y nada elegante: **Amazon SES arranca en modo
sandbox**, y en sandbox solo entrega a direcciones que hayas verificado tu mismo a
mano. Para Koda eso no es una limitacion menor, es la puerta cerrada: la unica forma
de entrar es un enlace magico por correo, asi que con SES en sandbox **nadie a quien
no conozcas de antemano puede usar la aplicacion**. Ni el evaluador de una prueba
tecnica, que es justo quien va a intentarlo.

Salir del sandbox se pide a AWS y lo aprueban ellos, cuando quieren. Este adaptador
es el seguro para mientras tanto, y a proposito habla SMTP en vez de la API de un
proveedor concreto: SMTP lo hablan Gmail, Brevo, SendGrid, Mailgun y el propio SES.
Cambiar de proveedor son cuatro variables de entorno y ni una linea de codigo.

Se usa la libreria estandar dentro de un hilo, como el adaptador de SES hace con
boto3 — no merece una dependencia nueva.
"""

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import Settings
from app.domain.ports.email_port import EmailPort


class SMTPEmail(EmailPort):
    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._puerto = settings.smtp_port
        self._usuario = settings.smtp_user
        self._password = settings.smtp_password
        # El remitente puede ser distinto del usuario que autentica, pero casi nunca
        # lo es: Gmail reescribe el From al de la cuenta y otros lo rechazan.
        self._de = settings.smtp_from or settings.smtp_user
        self._nombre = settings.ses_from_name

    def _construir(self, destinatario: str, asunto: str, texto: str, html: str | None) -> EmailMessage:
        mensaje = EmailMessage()
        mensaje["From"] = formataddr((self._nombre, self._de or ""))
        mensaje["To"] = destinatario
        mensaje["Subject"] = asunto
        # El texto plano va primero y el HTML como alternativa: es el orden que exige
        # el formato, y ademas el que decide que ve un cliente que no pinta HTML.
        mensaje.set_content(texto)
        if html is not None:
            mensaje.add_alternative(html, subtype="html")
        return mensaje

    async def enviar(self, destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
        if not (self._host and self._usuario and self._password):
            raise ValueError("SMTP_HOST, SMTP_USER y SMTP_PASSWORD no estan configurados")
        mensaje = self._construir(destinatario, asunto, texto, html)
        await asyncio.to_thread(self._enviar_sync, mensaje)

    def _enviar_sync(self, mensaje: EmailMessage) -> None:
        # 465 es SMTPS (TLS desde el primer byte); 587 empieza en claro y sube a TLS
        # con STARTTLS. Mandar por 587 sin starttls() entregaria la contraseña en
        # claro, asi que la eleccion se hace por puerto y no se deja al azar.
        if self._puerto == 465:
            with smtplib.SMTP_SSL(self._host, self._puerto, timeout=20) as servidor:
                servidor.login(self._usuario, self._password)
                servidor.send_message(mensaje)
            return
        with smtplib.SMTP(self._host, self._puerto, timeout=20) as servidor:
            servidor.starttls()
            servidor.login(self._usuario, self._password)
            servidor.send_message(mensaje)

"""Caso de uso: solicitar un enlace magico de acceso.

Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §3. Siempre "tiene exito" desde fuera
(nunca revela si el correo existe, ni si se alcanzo el rate limit) para no permitir
enumeracion de usuarios ni sondeo del limite.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.domain.ports.email_port import EmailPort
from app.domain.ports.repositories import RunnerRepo, TokenAccesoRepo


def _crear_token() -> tuple[str, str]:
    """Devuelve (token_en_claro, hash_para_bd). Nunca random ni uuid4 para el secreto."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


async def solicitar_enlace(
    email: str,
    ip: str | None,
    *,
    runners: RunnerRepo,
    tokens: TokenAccesoRepo,
    email_port: EmailPort,
    settings: Settings,
) -> None:
    email_normalizado = email.strip().lower()
    runner = await runners.crear_o_actualizar_acceso(email_normalizado)

    ahora = datetime.now(UTC)
    hace_una_hora = ahora - timedelta(hours=1)

    en_limite_por_correo = (
        await tokens.contar_creados_desde(hace_una_hora, runner_id=runner.id)
    ) >= settings.rate_limit_magic_links_per_hour
    en_limite_por_ip = ip is not None and (
        await tokens.contar_creados_desde(hace_una_hora, ip_solicitud=ip)
    ) >= settings.rate_limit_magic_links_per_hour_ip

    if en_limite_por_correo or en_limite_por_ip:
        return  # silencioso a proposito: no revela ni confirma ni delata el limite

    token, token_hash = _crear_token()
    expira_en = ahora + timedelta(minutes=settings.magic_link_ttl_minutes)
    await tokens.crear(runner.id, token_hash, expira_en, ip)

    enlace = f"{settings.app_base_url}/api/auth/canjear?token={token}"
    await email_port.enviar(
        destinatario=runner.email,
        asunto="Tu enlace de acceso a Koda",
        texto=(
            f"Hola,\n\nEntra a Koda con este enlace (valido {settings.magic_link_ttl_minutes} minutos):\n"
            f"{enlace}\n\nSi no lo pediste tu, ignora este correo."
        ),
    )

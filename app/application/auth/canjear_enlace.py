"""Caso de uso: canjear un enlace magico por una sesion.

Un solo uso, comprobacion de expiracion, comparacion del hash en tiempo constante
la hace el propio lookup por indice — el secreto nunca se compara en claro.
Ver docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md §3.
"""

import hashlib
from datetime import UTC, datetime

from app.domain.models import Runner
from app.domain.ports.repositories import RunnerRepo, TokenAccesoRepo


async def canjear_enlace(
    token: str,
    *,
    tokens: TokenAccesoRepo,
    runners: RunnerRepo,
) -> Runner | None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    registro = await tokens.obtener_por_hash(token_hash)
    if registro is None:
        return None

    ahora = datetime.now(UTC)
    if not registro.esta_vigente(ahora):
        return None

    runner = await runners.obtener(registro.runner_id)
    if runner is None or not runner.activo:
        return None

    await tokens.marcar_usado(registro.id, ahora)
    return runner

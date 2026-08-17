"""Caso de uso: canjear un enlace magico por una sesion.

El token vale mientras no caduque y admite mas de un canje dentro de esa ventana
(ADR-024). El secreto nunca se compara en claro: se busca por hash, y la comparacion
en tiempo constante la hace el propio indice.
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

    # Solo la primera vez: `usado_en` es un dato de auditoria — cuando se estreno este
    # enlace — y sobrescribirlo en cada canje lo convertiria en "la ultima vez", que no
    # es lo que dice el nombre ni lo que sirve para investigar nada.
    if registro.usado_en is None:
        await tokens.marcar_usado(registro.id, ahora)
    return runner

"""recordatorios

Revision ID: d4a1b8c05e37
Revises: c7e2f04b91aa
Create Date: 2026-08-14 12:05:44.201883

La agenda de avisos de docs/contexto/02-DOMINIO-RUNNING.md §4. La hora se guarda en
LOCAL del runner y no en UTC: la conversion depende de su zona horaria, que puede
cambiar (viaja, o entra el horario de verano), y guardarla convertida obligaria a
recalcular todas las filas cada vez.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4a1b8c05e37"
down_revision: str | Sequence[str] | None = "c7e2f04b91aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recordatorios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("hora_local", sa.Time(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ultima_ejecucion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Dos filas "diario" del mismo runner serian dos correos iguales cada mañana.
        sa.UniqueConstraint("runner_id", "tipo", name="uq_recordatorio_runner_tipo"),
    )
    op.create_index("idx_recordatorios_runner", "recordatorios", ["runner_id"])
    # El scheduler arranca preguntando "a quien hay que escribir": esa consulta filtra
    # por activo y no por runner, y es la unica del proyecto que cruza usuarios.
    op.create_index("idx_recordatorios_activos", "recordatorios", ["activo"])


def downgrade() -> None:
    op.drop_table("recordatorios")

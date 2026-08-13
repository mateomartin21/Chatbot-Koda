"""runners y tokens_acceso

Revision ID: f9f7bd20dec0
Revises:
Create Date: 2026-08-13 00:40:51.390012

Escrita a mano (no autogenerada): no habia una instancia de Postgres viva
para que Alembic introspeccionara el esquema. Refleja app/infrastructure/persistence/orm.py
y docs/contexto/02-DOMINIO-RUNNING.md §4.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f9f7bd20dec0"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("edad", sa.Integer(), nullable=True),
        sa.Column("nivel", sa.String(), nullable=True),
        sa.Column("dias_disponibles", sa.Integer(), nullable=True),
        sa.Column("zona_horaria", sa.String(), nullable=True),
        sa.Column("marca_distancia_km", sa.Float(), nullable=True),
        sa.Column("marca_tiempo_seg", sa.Float(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ultimo_acceso", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("idx_runners_email", "runners", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "tokens_acceso",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_solicitud", sa.String(), nullable=True),
    )
    op.create_index("idx_tokens_acceso_runner", "tokens_acceso", ["runner_id"])
    op.create_index("idx_tokens_acceso_hash", "tokens_acceso", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("tokens_acceso")
    op.drop_index("idx_runners_email", table_name="runners")
    op.drop_table("runners")

"""conversaciones y memoria_hechos

Revision ID: c7e2f04b91aa
Revises: b3c1a7e94f2d
Create Date: 2026-08-13 23:41:12.884201

Las capas 2 y 3 de docs/contexto/05-MEMORIA.md. Los dos indices son los que pide
02-DOMINIO-RUNNING §4: las dos consultas calientes son "los ultimos N turnos de este
runner" y "sus hechos vigentes", y las dos van por runner.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c7e2f04b91aa"
down_revision: str | Sequence[str] | None = "b3c1a7e94f2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversaciones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column("rol", sa.String(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("modalidad", sa.String(), nullable=False, server_default="texto"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_conversaciones_runner_fecha",
        "conversaciones",
        ["runner_id", sa.text("creado_en DESC")],
    )

    op.create_table(
        "memoria_hechos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("hecho", sa.Text(), nullable=False),
        sa.Column("confianza", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("idx_hechos_runner_vigente", "memoria_hechos", ["runner_id", "vigente"])


def downgrade() -> None:
    op.drop_table("memoria_hechos")
    op.drop_table("conversaciones")

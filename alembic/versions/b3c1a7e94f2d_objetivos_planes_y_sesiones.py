"""objetivos, planes y sesiones

Revision ID: b3c1a7e94f2d
Revises: f9f7bd20dec0
Create Date: 2026-08-13 11:20:04.118373

Escrita a mano, como la primera: no hay una instancia de Postgres viva contra la que
autogenerar. Refleja app/infrastructure/persistence/orm.py y el modelo de datos de
docs/contexto/02-DOMINIO-RUNNING.md §4, incluidos sus indices.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b3c1a7e94f2d"
down_revision: str | Sequence[str] | None = "f9f7bd20dec0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "objetivos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column("distancia_km", sa.Float(), nullable=False),
        sa.Column("fecha_carrera", sa.Date(), nullable=False),
        sa.Column("nombre_carrera", sa.String(), nullable=True),
        sa.Column("tiempo_meta_seg", sa.Float(), nullable=True),
        sa.Column("estado", sa.String(), nullable=False, server_default="activo"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_objetivos_runner_estado", "objetivos", ["runner_id", "estado"])

    op.create_table(
        "planes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column(
            "objetivo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("objetivos.id"), nullable=False
        ),
        sa.Column("semanas", sa.Integer(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("generado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ritmos_estimados", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("zonas", sa.JSON(), nullable=False),
        sa.Column("semanas_especiales", sa.JSON(), nullable=False),
        sa.Column("notas", sa.JSON(), nullable=False),
    )
    op.create_index("idx_planes_runner", "planes", ["runner_id"])
    op.create_index("idx_planes_objetivo", "planes", ["objetivo_id"])

    op.create_table(
        "sesiones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("planes.id"), nullable=False),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runners.id"), nullable=False),
        sa.Column("semana", sa.Integer(), nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("distancia_km", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duracion_min", sa.Integer(), nullable=True),
        sa.Column("ritmo_objetivo_seg_km", sa.Float(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=False, server_default=""),
        sa.Column("fecha_programada", sa.Date(), nullable=False),
        sa.Column("completada", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # El indice que pide 02-DOMINIO-RUNNING.md §4: la consulta caliente es "que le toca
    # hoy a este runner", y va por runner y fecha, nunca por plan.
    op.create_index("idx_sesiones_runner_fecha", "sesiones", ["runner_id", "fecha_programada"])
    op.create_index("idx_sesiones_plan", "sesiones", ["plan_id"])


def downgrade() -> None:
    op.drop_table("sesiones")
    op.drop_table("planes")
    op.drop_table("objetivos")

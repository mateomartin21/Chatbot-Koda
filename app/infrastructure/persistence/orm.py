"""Modelos SQLAlchemy. Reflejan el esquema de docs/contexto/02-DOMINIO-RUNNING.md §4."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunnerORM(Base):
    __tablename__ = "runners"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # La unicidad real es case-insensitive y vive en la migracion (indice sobre lower(email)),
    # no aqui, para tener una sola fuente de verdad.
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    edad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nivel: Mapped[str | None] = mapped_column(String, nullable=True)
    dias_disponibles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zona_horaria: Mapped[str | None] = mapped_column(String, nullable=True)
    marca_distancia_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    marca_tiempo_seg: Mapped[float | None] = mapped_column(Float, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TokenAccesoORM(Base):
    __tablename__ = "tokens_acceso"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_solicitud: Mapped[str | None] = mapped_column(String, nullable=True)

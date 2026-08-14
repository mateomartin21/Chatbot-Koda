"""Modelos SQLAlchemy. Reflejan el esquema de docs/contexto/02-DOMINIO-RUNNING.md §4."""

from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
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


class ConversacionORM(Base):
    """Capa 2 de la memoria: la ventana corta. Ver docs/contexto/05-MEMORIA.md §2."""

    __tablename__ = "conversaciones"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    rol: Mapped[str] = mapped_column(String, nullable=False)  # "usuario" | "coach"
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    modalidad: Mapped[str] = mapped_column(String, nullable=False, default="texto")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoriaHechoORM(Base):
    """Capa 3: lo que trasciende la sesion. Los hechos no se borran, se marcan no
    vigentes — se conserva la historia y se deja de inyectar lo que ya no es cierto
    (docs/contexto/05-MEMORIA.md §4.1)."""

    __tablename__ = "memoria_hechos"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    categoria: Mapped[str] = mapped_column(String, nullable=False)
    hecho: Mapped[str] = mapped_column(Text, nullable=False)
    confianza: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    vigente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RecordatorioORM(Base):
    __tablename__ = "recordatorios"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)  # diario | checkin | semanal
    # Hora LOCAL del runner, no UTC: la conversion se hace al programar el envio, con
    # la zona horaria que tenga en ese momento. Guardarla ya convertida obligaria a
    # recalcular todas las filas cada vez que alguien viaja o cambia el horario de verano.
    hora_local: Mapped[time] = mapped_column(Time, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ultima_ejecucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Un recordatorio por tipo y runner: si no, dos filas "diario" mandan dos correos.
        UniqueConstraint("runner_id", "tipo", name="uq_recordatorio_runner_tipo"),
    )


class ObjetivoORM(Base):
    __tablename__ = "objetivos"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    distancia_km: Mapped[float] = mapped_column(Float, nullable=False)
    fecha_carrera: Mapped[date] = mapped_column(Date, nullable=False)
    nombre_carrera: Mapped[str | None] = mapped_column(String, nullable=True)
    tiempo_meta_seg: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="activo")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanORM(Base):
    __tablename__ = "planes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    objetivo_id: Mapped[UUID] = mapped_column(ForeignKey("objetivos.id"), nullable=False, index=True)
    semanas: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ritmos_estimados: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Las cinco zonas en seg/km. JSON y no cinco columnas porque son un value object
    # que se lee y se escribe entero: partirlo solo daria mas sitios donde equivocarse.
    zonas: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # {"descarga": [4, 8], "taper": [11, 12]} — atributos de la semana, no de la sesion.
    # Guardarlos en cada fila de sesiones seria repetir el mismo dato siete veces.
    semanas_especiales: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    notas: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class SesionORM(Base):
    __tablename__ = "sesiones"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("planes.id"), nullable=False, index=True)
    # Redundante con plan_id, y a proposito: permite filtrar sesiones por runner sin
    # pasar por planes, que es justo lo que hace idx_sesiones_runner_fecha.
    runner_id: Mapped[UUID] = mapped_column(ForeignKey("runners.id"), nullable=False, index=True)
    semana: Mapped[int] = mapped_column(Integer, nullable=False)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    distancia_km: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duracion_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ritmo_objetivo_seg_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fecha_programada: Mapped[date] = mapped_column(Date, nullable=False)
    completada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

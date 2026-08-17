"""Implementaciones concretas de los puertos de repositorio, con SQLAlchemy async."""

from collections.abc import Sequence
from dataclasses import fields
from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    DatosPerfil,
    Hecho,
    Mensaje,
    Recordatorio,
    Runner,
    TipoRecordatorio,
    TokenAcceso,
    normalizar_hecho,
)
from app.domain.ports.repositories import (
    ConversacionRepo,
    MemoriaRepo,
    PlanRepo,
    RecordatorioRepo,
    RunnerRepo,
    TokenAccesoRepo,
)
from app.domain.training.modelos import (
    Distancia,
    EstadoObjetivo,
    Objetivo,
    PlanActivo,
    PlanEntrenamiento,
    SemanaPlan,
    Sesion,
    SesionProgramada,
    TipoSesion,
)
from app.domain.training.paces import Ritmo, ZonasRitmo
from app.infrastructure.persistence.orm import (
    ConversacionORM,
    MemoriaHechoORM,
    ObjetivoORM,
    PlanORM,
    RecordatorioORM,
    RunnerORM,
    SesionORM,
    TokenAccesoORM,
)


def _runner_a_dominio(fila: RunnerORM) -> Runner:
    return Runner(
        id=fila.id,
        email=fila.email,
        creado_en=fila.creado_en,
        activo=fila.activo,
        ultimo_acceso=fila.ultimo_acceso,
        nombre=fila.nombre,
        edad=fila.edad,
        nivel=fila.nivel,
        dias_disponibles=fila.dias_disponibles,
        zona_horaria=fila.zona_horaria,
        marca_distancia_km=fila.marca_distancia_km,
        marca_tiempo_seg=fila.marca_tiempo_seg,
    )


def _token_a_dominio(fila: TokenAccesoORM) -> TokenAcceso:
    return TokenAcceso(
        id=fila.id,
        runner_id=fila.runner_id,
        token_hash=fila.token_hash,
        expira_en=fila.expira_en,
        creado_en=fila.creado_en,
        ip_solicitud=fila.ip_solicitud,
        usado_en=fila.usado_en,
    )


class SqlRunnerRepo(RunnerRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obtener(self, runner_id: UUID) -> Runner | None:
        fila = await self._session.get(RunnerORM, runner_id)
        return _runner_a_dominio(fila) if fila else None

    async def obtener_por_email(self, email: str) -> Runner | None:
        stmt = select(RunnerORM).where(func.lower(RunnerORM.email) == email.lower())
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        return _runner_a_dominio(fila) if fila else None

    async def crear_o_actualizar_acceso(self, email: str) -> Runner:
        email_normalizado = email.lower().strip()
        stmt = select(RunnerORM).where(func.lower(RunnerORM.email) == email_normalizado)
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        ahora = datetime.now(UTC)
        if fila is None:
            fila = RunnerORM(id=uuid4(), email=email_normalizado, ultimo_acceso=ahora)
            self._session.add(fila)
        else:
            fila.ultimo_acceso = ahora
        await self._session.commit()
        await self._session.refresh(fila)
        return _runner_a_dominio(fila)

    async def actualizar_perfil(self, runner_id: UUID, datos: DatosPerfil) -> Runner:
        fila = await self._session.get(RunnerORM, runner_id)
        if fila is None:
            raise LookupError(f"No existe el runner {runner_id}")
        for campo in fields(datos):
            valor = getattr(datos, campo.name)
            if valor is not None:
                setattr(fila, campo.name, valor)
        await self._session.commit()
        await self._session.refresh(fila)
        return _runner_a_dominio(fila)


class SqlTokenAccesoRepo(TokenAccesoRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(
        self, runner_id: UUID, token_hash: str, expira_en: datetime, ip_solicitud: str | None
    ) -> TokenAcceso:
        fila = TokenAccesoORM(
            id=uuid4(),
            runner_id=runner_id,
            token_hash=token_hash,
            expira_en=expira_en,
            ip_solicitud=ip_solicitud,
        )
        self._session.add(fila)
        await self._session.commit()
        await self._session.refresh(fila)
        return _token_a_dominio(fila)

    async def obtener_por_hash(self, token_hash: str) -> TokenAcceso | None:
        stmt = select(TokenAccesoORM).where(TokenAccesoORM.token_hash == token_hash)
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        return _token_a_dominio(fila) if fila else None

    async def marcar_usado(self, token_id: UUID, usado_en: datetime) -> None:
        fila = await self._session.get(TokenAccesoORM, token_id)
        if fila is not None:
            fila.usado_en = usado_en
            await self._session.commit()

    async def contar_creados_desde(
        self, desde: datetime, runner_id: UUID | None = None, ip_solicitud: str | None = None
    ) -> int:
        stmt = select(func.count()).select_from(TokenAccesoORM).where(TokenAccesoORM.creado_en >= desde)
        if runner_id is not None:
            stmt = stmt.where(TokenAccesoORM.runner_id == runner_id)
        if ip_solicitud is not None:
            stmt = stmt.where(TokenAccesoORM.ip_solicitud == ip_solicitud)
        return (await self._session.execute(stmt)).scalar_one()


# --- Plan de entrenamiento ------------------------------------------------------


def _zonas_a_json(zonas: ZonasRitmo) -> dict[str, float | bool]:
    return {
        "facil": zonas.facil.seg_por_km,
        "larga": zonas.larga.seg_por_km,
        "tempo": zonas.tempo.seg_por_km,
        "intervalos": zonas.intervalos.seg_por_km,
        "objetivo": zonas.objetivo.seg_por_km,
        "estimados": zonas.estimados,
    }


def _zonas_a_dominio(datos: dict) -> ZonasRitmo:
    return ZonasRitmo(
        facil=Ritmo(datos["facil"]),
        larga=Ritmo(datos["larga"]),
        tempo=Ritmo(datos["tempo"]),
        intervalos=Ritmo(datos["intervalos"]),
        objetivo=Ritmo(datos["objetivo"]),
        estimados=bool(datos.get("estimados", False)),
    )


def _sesion_a_dominio(fila: SesionORM) -> Sesion:
    return Sesion(
        dia_semana=fila.dia_semana,
        tipo=TipoSesion(fila.tipo),
        distancia_km=fila.distancia_km,
        descripcion=fila.descripcion,
        ritmo_objetivo_seg_km=fila.ritmo_objetivo_seg_km,
    )


def _plan_a_dominio(objetivo: ObjetivoORM, plan: PlanORM, sesiones: list[SesionORM]) -> PlanActivo:
    descarga = set(plan.semanas_especiales.get("descarga", []))
    taper = set(plan.semanas_especiales.get("taper", []))
    numeros = sorted({s.semana for s in sesiones})
    semanas = tuple(
        SemanaPlan(
            numero=numero,
            sesiones=tuple(
                _sesion_a_dominio(f)
                for f in sorted((s for s in sesiones if s.semana == numero), key=lambda s: s.dia_semana)
            ),
            es_descarga=numero in descarga,
            es_taper=numero in taper,
        )
        for numero in numeros
    )
    return PlanActivo(
        id=plan.id,
        objetivo=Objetivo(
            distancia=Distancia.desde_km(objetivo.distancia_km),
            fecha_carrera=objetivo.fecha_carrera,
            nombre_carrera=objetivo.nombre_carrera,
            tiempo_meta_seg=objetivo.tiempo_meta_seg,
        ),
        plan=PlanEntrenamiento(
            distancia=Distancia.desde_km(objetivo.distancia_km),
            semanas=semanas,
            zonas=_zonas_a_dominio(plan.zonas),
            ritmos_estimados=plan.ritmos_estimados,
            notas=tuple(plan.notas),
        ),
        fecha_inicio=plan.fecha_inicio,
        generado_en=plan.generado_en,
        version=plan.version,
        completadas=frozenset((s.semana, s.dia_semana) for s in sesiones if s.completada),
    )


class SqlPlanRepo(PlanRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(
        self, runner_id: UUID, objetivo: Objetivo, plan: PlanEntrenamiento, fecha_inicio: date
    ) -> PlanActivo:
        # Un plan nuevo jubila al anterior. No se borra: el historial de objetivos es
        # justo lo que permitira decir mas adelante "ya preparaste un 10K en marzo".
        anteriores = await self._session.execute(
            select(ObjetivoORM).where(
                ObjetivoORM.runner_id == runner_id,
                ObjetivoORM.estado == EstadoObjetivo.ACTIVO.value,
            )
        )
        for fila in anteriores.scalars():
            fila.estado = EstadoObjetivo.ABANDONADO.value

        version = (
            await self._session.execute(
                select(func.coalesce(func.max(PlanORM.version), 0)).where(PlanORM.runner_id == runner_id)
            )
        ).scalar_one() + 1

        objetivo_orm = ObjetivoORM(
            id=uuid4(),
            runner_id=runner_id,
            distancia_km=objetivo.distancia.km,
            fecha_carrera=objetivo.fecha_carrera,
            nombre_carrera=objetivo.nombre_carrera,
            tiempo_meta_seg=objetivo.tiempo_meta_seg,
            estado=EstadoObjetivo.ACTIVO.value,
        )
        self._session.add(objetivo_orm)

        plan_orm = PlanORM(
            id=uuid4(),
            runner_id=runner_id,
            objetivo_id=objetivo_orm.id,
            semanas=len(plan.semanas),
            fecha_inicio=fecha_inicio,
            generado_en=datetime.now(UTC),
            version=version,
            ritmos_estimados=plan.ritmos_estimados,
            zonas=_zonas_a_json(plan.zonas),
            semanas_especiales={
                "descarga": [s.numero for s in plan.semanas if s.es_descarga],
                "taper": [s.numero for s in plan.semanas if s.es_taper],
            },
            notas=list(plan.notas),
        )
        self._session.add(plan_orm)

        # Las fechas las pone el dominio, no este repositorio: PlanActivo ya sabe
        # convertir "semana 3, dia 6" en un dia concreto y descartar lo que caeria
        # despues de la carrera. Aqui solo se persiste lo que decida.
        calendario = PlanActivo(
            id=plan_orm.id,
            objetivo=objetivo,
            plan=plan,
            fecha_inicio=fecha_inicio,
            generado_en=plan_orm.generado_en,
            version=version,
        )
        for programada in calendario.sesiones_programadas(incluir_descansos=True):
            self._session.add(
                SesionORM(
                    id=uuid4(),
                    plan_id=plan_orm.id,
                    runner_id=runner_id,
                    semana=programada.semana,
                    dia_semana=programada.sesion.dia_semana,
                    tipo=programada.sesion.tipo.value,
                    distancia_km=programada.sesion.distancia_km,
                    ritmo_objetivo_seg_km=programada.sesion.ritmo_objetivo_seg_km,
                    descripcion=programada.sesion.descripcion,
                    fecha_programada=programada.fecha,
                )
            )

        await self._session.commit()
        guardado = await self.obtener_activo(runner_id)
        assert guardado is not None  # acabamos de guardarlo en esta misma transaccion
        return guardado

    async def obtener_activo(self, runner_id: UUID) -> PlanActivo | None:
        stmt = (
            select(PlanORM, ObjetivoORM)
            .join(ObjetivoORM, PlanORM.objetivo_id == ObjetivoORM.id)
            .where(
                PlanORM.runner_id == runner_id,
                ObjetivoORM.estado == EstadoObjetivo.ACTIVO.value,
            )
            .order_by(PlanORM.version.desc())
            .limit(1)
        )
        fila = (await self._session.execute(stmt)).first()
        if fila is None:
            return None
        plan_orm, objetivo_orm = fila
        sesiones = (
            (
                await self._session.execute(
                    select(SesionORM).where(
                        SesionORM.plan_id == plan_orm.id,
                        SesionORM.runner_id == runner_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return _plan_a_dominio(objetivo_orm, plan_orm, list(sesiones))

    async def proxima_sesion(self, runner_id: UUID, desde: date) -> SesionProgramada | None:
        """Consulta directa por (runner_id, fecha_programada) — el indice existe para
        esto. Reconstruir el plan entero para leer una fila seria trabajo de mas."""
        stmt = (
            select(SesionORM)
            .join(PlanORM, SesionORM.plan_id == PlanORM.id)
            .join(ObjetivoORM, PlanORM.objetivo_id == ObjetivoORM.id)
            .where(
                SesionORM.runner_id == runner_id,
                SesionORM.fecha_programada >= desde,
                SesionORM.completada.is_(False),
                SesionORM.tipo != TipoSesion.DESCANSO.value,
                ObjetivoORM.estado == EstadoObjetivo.ACTIVO.value,
            )
            .order_by(SesionORM.fecha_programada)
            .limit(1)
        )
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        if fila is None:
            return None
        return SesionProgramada(
            sesion=_sesion_a_dominio(fila),
            semana=fila.semana,
            fecha=fila.fecha_programada,
            completada=fila.completada,
        )

    # --- Memoria (docs/contexto/05-MEMORIA.md) --------------------------------------

    async def marcar_completada(self, runner_id: UUID, fecha: date) -> SesionProgramada | None:
        # runner_id en el WHERE aunque la fecha ya acote bastante: sin el, bastaria
        # con acertar un dia para marcar la sesion de otra persona.
        fila = (
            await self._session.execute(
                select(SesionORM).where(
                    SesionORM.runner_id == runner_id,
                    SesionORM.fecha_programada == fecha,
                    SesionORM.tipo != TipoSesion.DESCANSO.value,
                )
            )
        ).scalar_one_or_none()
        if fila is None:
            return None

        fila.completada = True
        await self._session.flush()

        activo = await self.obtener_activo(runner_id)
        if activo is None:
            return None
        return next(
            (s for s in activo.sesiones_programadas() if s.fecha == fecha),
            None,
        )


class SqlConversacionRepo(ConversacionRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, runner_id: UUID, mensajes: Sequence[Mensaje]) -> None:
        for mensaje in mensajes:
            self._session.add(
                ConversacionORM(
                    id=uuid4(),
                    runner_id=runner_id,
                    rol=mensaje.rol,
                    contenido=mensaje.contenido,
                    modalidad=mensaje.modalidad,
                    creado_en=mensaje.creado_en or datetime.now(UTC),
                )
            )
        await self._session.commit()

    async def ultimos(self, runner_id: UUID, limite: int = 10) -> list[Mensaje]:
        # Se piden los mas RECIENTES (creado_en DESC, que es como esta el indice) y se
        # devuelven al reves: el modelo necesita leerlos en el orden en que ocurrieron.
        stmt = (
            select(ConversacionORM)
            .where(ConversacionORM.runner_id == runner_id)
            .order_by(ConversacionORM.creado_en.desc(), ConversacionORM.id.desc())
            .limit(limite)
        )
        filas = (await self._session.execute(stmt)).scalars().all()
        return [
            Mensaje(
                rol=f.rol,
                contenido=f.contenido,
                modalidad=f.modalidad,
                creado_en=f.creado_en,
            )
            for f in reversed(filas)
        ]

    async def borrar(self, runner_id: UUID) -> int:
        # El WHERE por runner_id no es una optimizacion, es la frontera de aislamiento:
        # un DELETE sin el borraria las conversaciones de todo el mundo. Por eso el
        # metodo del puerto lo lleva en la firma y no puede llamarse sin el.
        resultado = await self._session.execute(
            delete(ConversacionORM).where(ConversacionORM.runner_id == runner_id)
        )
        await self._session.commit()
        return resultado.rowcount or 0


class SqlMemoriaRepo(MemoriaRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, runner_id: UUID, hechos: Sequence[Hecho]) -> int:
        existentes = (
            (
                await self._session.execute(
                    select(MemoriaHechoORM).where(
                        MemoriaHechoORM.runner_id == runner_id,
                        MemoriaHechoORM.vigente.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        conocidos = {(f.categoria, normalizar_hecho(f.hecho)) for f in existentes}

        guardados = 0
        for hecho in hechos:
            clave = (hecho.categoria, normalizar_hecho(hecho.hecho))
            if clave in conocidos:
                continue
            conocidos.add(clave)
            self._session.add(
                MemoriaHechoORM(
                    id=uuid4(),
                    runner_id=runner_id,
                    categoria=hecho.categoria,
                    hecho=hecho.hecho,
                    confianza=hecho.confianza,
                    vigente=hecho.vigente,
                )
            )
            guardados += 1
        if guardados:
            await self._session.commit()
        return guardados

    async def vigentes(self, runner_id: UUID, limite: int = 25) -> list[Hecho]:
        stmt = (
            select(MemoriaHechoORM)
            .where(MemoriaHechoORM.runner_id == runner_id, MemoriaHechoORM.vigente.is_(True))
            .order_by(MemoriaHechoORM.creado_en.desc())
            .limit(limite)
        )
        filas = (await self._session.execute(stmt)).scalars().all()
        return [
            Hecho(
                categoria=f.categoria,
                hecho=f.hecho,
                confianza=f.confianza,
                vigente=f.vigente,
                creado_en=f.creado_en,
            )
            for f in filas
        ]


# --- Recordatorios --------------------------------------------------------------


def _recordatorio_a_dominio(fila: RecordatorioORM) -> Recordatorio:
    return Recordatorio(
        id=fila.id,
        runner_id=fila.runner_id,
        tipo=TipoRecordatorio(fila.tipo),
        hora_local=fila.hora_local,
        activo=fila.activo,
        ultima_ejecucion=fila.ultima_ejecucion,
    )


class SqlRecordatorioRepo(RecordatorioRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def de_runner(self, runner_id: UUID) -> list[Recordatorio]:
        stmt = select(RecordatorioORM).where(RecordatorioORM.runner_id == runner_id)
        return [_recordatorio_a_dominio(f) for f in (await self._session.execute(stmt)).scalars()]

    async def guardar(
        self, runner_id: UUID, tipo: TipoRecordatorio, hora_local: time, activo: bool
    ) -> Recordatorio:
        stmt = select(RecordatorioORM).where(
            RecordatorioORM.runner_id == runner_id,
            RecordatorioORM.tipo == tipo.value,
        )
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        if fila is None:
            fila = RecordatorioORM(
                id=uuid4(), runner_id=runner_id, tipo=tipo.value, hora_local=hora_local, activo=activo
            )
            self._session.add(fila)
        else:
            fila.hora_local = hora_local
            fila.activo = activo
        await self._session.commit()
        await self._session.refresh(fila)
        return _recordatorio_a_dominio(fila)

    async def desactivar_todos(self, runner_id: UUID) -> int:
        stmt = select(RecordatorioORM).where(
            RecordatorioORM.runner_id == runner_id, RecordatorioORM.activo.is_(True)
        )
        filas = (await self._session.execute(stmt)).scalars().all()
        for fila in filas:
            fila.activo = False
        if filas:
            await self._session.commit()
        return len(filas)

    async def marcar_enviado(self, runner_id: UUID, tipo: TipoRecordatorio, cuando: datetime) -> None:
        stmt = select(RecordatorioORM).where(
            RecordatorioORM.runner_id == runner_id, RecordatorioORM.tipo == tipo.value
        )
        fila = (await self._session.execute(stmt)).scalar_one_or_none()
        if fila is not None:
            fila.ultima_ejecucion = cuando
            await self._session.commit()

    async def activos_de_todos(self) -> list[Recordatorio]:
        stmt = select(RecordatorioORM).where(RecordatorioORM.activo.is_(True))
        return [_recordatorio_a_dominio(f) for f in (await self._session.execute(stmt)).scalars()]

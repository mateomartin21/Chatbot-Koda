"""Dobles en memoria para tests. Sin red, sin BD — ver docs/contexto/08-CONVENCIONES.md."""

from collections.abc import Sequence
from dataclasses import fields, replace
from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

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
from app.domain.training.modelos import Objetivo, PlanActivo, PlanEntrenamiento, SesionProgramada


class InMemoryRunnerRepo(RunnerRepo):
    def __init__(self) -> None:
        self._runners: dict[UUID, Runner] = {}

    async def obtener(self, runner_id: UUID) -> Runner | None:
        return self._runners.get(runner_id)

    async def obtener_por_email(self, email: str) -> Runner | None:
        email = email.lower()
        return next((r for r in self._runners.values() if r.email == email), None)

    async def crear_o_actualizar_acceso(self, email: str) -> Runner:
        email = email.strip().lower()
        existente = await self.obtener_por_email(email)
        ahora = datetime.now(UTC)
        if existente is not None:
            existente.ultimo_acceso = ahora
            return existente
        runner = Runner(id=uuid4(), email=email, creado_en=ahora, ultimo_acceso=ahora)
        self._runners[runner.id] = runner
        return runner

    async def actualizar_perfil(self, runner_id: UUID, datos: DatosPerfil) -> Runner:
        runner = self._runners[runner_id]
        cambios = {
            campo.name: getattr(datos, campo.name)
            for campo in fields(datos)
            if getattr(datos, campo.name) is not None
        }
        self._runners[runner_id] = replace(runner, **cambios)
        return self._runners[runner_id]

    def agregar(self, runner: Runner) -> None:
        self._runners[runner.id] = runner


class InMemoryTokenAccesoRepo(TokenAccesoRepo):
    def __init__(self) -> None:
        self._tokens: dict[UUID, TokenAcceso] = {}

    async def crear(
        self, runner_id: UUID, token_hash: str, expira_en: datetime, ip_solicitud: str | None
    ) -> TokenAcceso:
        token = TokenAcceso(
            id=uuid4(),
            runner_id=runner_id,
            token_hash=token_hash,
            expira_en=expira_en,
            creado_en=datetime.now(UTC),
            ip_solicitud=ip_solicitud,
        )
        self._tokens[token.id] = token
        return token

    async def obtener_por_hash(self, token_hash: str) -> TokenAcceso | None:
        return next((t for t in self._tokens.values() if t.token_hash == token_hash), None)

    async def marcar_usado(self, token_id: UUID, usado_en: datetime) -> None:
        if token_id in self._tokens:
            self._tokens[token_id].usado_en = usado_en

    async def contar_creados_desde(
        self, desde: datetime, runner_id: UUID | None = None, ip_solicitud: str | None = None
    ) -> int:
        return sum(
            1
            for t in self._tokens.values()
            if t.creado_en >= desde
            and (runner_id is None or t.runner_id == runner_id)
            and (ip_solicitud is None or t.ip_solicitud == ip_solicitud)
        )

    def agregar(self, token: TokenAcceso) -> None:
        self._tokens[token.id] = token


class InMemoryPlanRepo(PlanRepo):
    """El plan activo de cada runner es el ultimo que guardo: es exactamente lo que
    hace SqlPlanRepo al jubilar los objetivos anteriores."""

    def __init__(self) -> None:
        self._por_runner: dict[UUID, list[PlanActivo]] = {}

    async def guardar(
        self, runner_id: UUID, objetivo: Objetivo, plan: PlanEntrenamiento, fecha_inicio: date
    ) -> PlanActivo:
        historial = self._por_runner.setdefault(runner_id, [])
        guardado = PlanActivo(
            id=uuid4(),
            objetivo=objetivo,
            plan=plan,
            fecha_inicio=fecha_inicio,
            generado_en=datetime.now(UTC),
            version=len(historial) + 1,
        )
        historial.append(guardado)
        return guardado

    async def obtener_activo(self, runner_id: UUID) -> PlanActivo | None:
        historial = self._por_runner.get(runner_id, [])
        return historial[-1] if historial else None

    async def proxima_sesion(self, runner_id: UUID, desde: date) -> SesionProgramada | None:
        activo = await self.obtener_activo(runner_id)
        return activo.proxima_sesion(desde) if activo else None

    async def marcar_completada(self, runner_id: UUID, fecha: date) -> SesionProgramada | None:
        activo = await self.obtener_activo(runner_id)
        if activo is None:
            return None
        hecha = next((s for s in activo.sesiones_programadas() if s.fecha == fecha), None)
        if hecha is None:
            return None

        # PlanActivo es inmutable: se sustituye por una copia con la sesion anadida al
        # conjunto de completadas, igual que hace el SQL al releer el plan entero.
        historial = self._por_runner[runner_id]
        historial[-1] = replace(
            activo, completadas=activo.completadas | {(hecha.semana, hecha.sesion.dia_semana)}
        )
        return next((s for s in historial[-1].sesiones_programadas() if s.fecha == fecha), None)


class InMemoryConversacionRepo(ConversacionRepo):
    def __init__(self) -> None:
        self._por_runner: dict[UUID, list[Mensaje]] = {}

    async def guardar(self, runner_id: UUID, mensajes: Sequence[Mensaje]) -> None:
        self._por_runner.setdefault(runner_id, []).extend(mensajes)

    async def ultimos(self, runner_id: UUID, limite: int = 10) -> list[Mensaje]:
        return self._por_runner.get(runner_id, [])[-limite:]


class InMemoryMemoriaRepo(MemoriaRepo):
    def __init__(self) -> None:
        self._por_runner: dict[UUID, list[Hecho]] = {}

    async def guardar(self, runner_id: UUID, hechos: Sequence[Hecho]) -> int:
        existentes = self._por_runner.setdefault(runner_id, [])
        conocidos = {(h.categoria, normalizar_hecho(h.hecho)) for h in existentes if h.vigente}
        guardados = 0
        for hecho in hechos:
            clave = (hecho.categoria, normalizar_hecho(hecho.hecho))
            if clave in conocidos:
                continue
            conocidos.add(clave)
            existentes.append(hecho)
            guardados += 1
        return guardados

    async def vigentes(self, runner_id: UUID, limite: int = 25) -> list[Hecho]:
        return [h for h in reversed(self._por_runner.get(runner_id, [])) if h.vigente][:limite]


class InMemoryRecordatorioRepo(RecordatorioRepo):
    def __init__(self) -> None:
        self._por_runner: dict[UUID, dict[TipoRecordatorio, Recordatorio]] = {}

    async def de_runner(self, runner_id: UUID) -> list[Recordatorio]:
        return list(self._por_runner.get(runner_id, {}).values())

    async def guardar(
        self, runner_id: UUID, tipo: TipoRecordatorio, hora_local: time, activo: bool
    ) -> Recordatorio:
        del_runner = self._por_runner.setdefault(runner_id, {})
        anterior = del_runner.get(tipo)
        recordatorio = Recordatorio(
            id=anterior.id if anterior else uuid4(),
            runner_id=runner_id,
            tipo=tipo,
            hora_local=hora_local,
            activo=activo,
            ultima_ejecucion=anterior.ultima_ejecucion if anterior else None,
        )
        del_runner[tipo] = recordatorio
        return recordatorio

    async def desactivar_todos(self, runner_id: UUID) -> int:
        del_runner = self._por_runner.get(runner_id, {})
        activos = [t for t, r in del_runner.items() if r.activo]
        for tipo in activos:
            del_runner[tipo] = replace(del_runner[tipo], activo=False)
        return len(activos)

    async def marcar_enviado(self, runner_id: UUID, tipo: TipoRecordatorio, cuando: datetime) -> None:
        del_runner = self._por_runner.get(runner_id, {})
        if tipo in del_runner:
            del_runner[tipo] = replace(del_runner[tipo], ultima_ejecucion=cuando)

    async def activos_de_todos(self) -> list[Recordatorio]:
        return [r for des in self._por_runner.values() for r in des.values() if r.activo]

"""Doble de VozRealtimePort. Sin red — ver docs/contexto/08-CONVENCIONES.md."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from app.domain.ports.llm_port import EjecutorHerramientas, Herramienta, LlamadaHerramienta
from app.domain.ports.voz_realtime_port import EventoVoz, SesionVozRealtime, VozRealtimePort


class FakeSesionVozRealtime(SesionVozRealtime):
    def __init__(
        self,
        eventos_a_emitir: list[EventoVoz] | None = None,
        *,
        ejecutar: EjecutorHerramientas | None = None,
        llamadas_a_emitir: list[LlamadaHerramienta] | None = None,
    ) -> None:
        self._eventos = eventos_a_emitir or []
        self.audio_recibido: list[bytes] = []
        self.texto_recibido: list[str] = []
        self.turno_terminado = False
        self.cerrada = False
        # Herramientas que este doble "decide" llamar antes de hablar, como haria el
        # modelo real. Sin esto no habia forma de probar el puente al entrenador
        # (ADR-020) ni el rescate del turno en que la voz no lo consulta.
        self._ejecutar = ejecutar
        self.llamadas_a_emitir = list(llamadas_a_emitir or [])
        self.resultados_recibidos: list[str] = []
        # Como el modelo real: no se responde nada hasta que llega algo de entrada.
        self._hay_entrada = asyncio.Event()

    async def enviar_audio(self, chunk: bytes) -> None:
        self.audio_recibido.append(chunk)
        self._hay_entrada.set()

    async def enviar_texto(self, texto: str) -> None:
        self.texto_recibido.append(texto)
        self._hay_entrada.set()

    async def terminar_turno_audio(self) -> None:
        self.turno_terminado = True

    async def eventos(self) -> AsyncIterator[EventoVoz]:
        await self._hay_entrada.wait()
        # Primero pide lo que necesita, despues habla. Es el orden del modelo real.
        for llamada in self.llamadas_a_emitir:
            if self._ejecutar is not None:
                self.resultados_recibidos.append(await self._ejecutar(llamada))
        for evento in self._eventos:
            yield evento

    async def cerrar(self) -> None:
        self.cerrada = True


class FakeVozRealtimePort(VozRealtimePort):
    def __init__(
        self,
        eventos_a_emitir: list[EventoVoz] | None = None,
        *,
        llamadas_a_emitir: list[LlamadaHerramienta] | None = None,
    ) -> None:
        self.falla_al_abrir = False
        self.eventos_a_emitir = eventos_a_emitir or []
        self.llamadas_a_emitir = list(llamadas_a_emitir or [])
        self.sesiones_abiertas: list[FakeSesionVozRealtime] = []
        self.prompts_recibidos: list[str] = []
        self.herramientas_recibidas: list[tuple[Herramienta, ...]] = []

    async def abrir_sesion(
        self,
        *,
        system_prompt: str,
        herramientas: Sequence[Herramienta] = (),
        ejecutar: EjecutorHerramientas | None = None,
    ) -> FakeSesionVozRealtime:
        if self.falla_al_abrir:
            raise RuntimeError("Nova Sonic no disponible")
        self.prompts_recibidos.append(system_prompt)
        self.herramientas_recibidas.append(tuple(herramientas))
        sesion = FakeSesionVozRealtime(
            self.eventos_a_emitir,
            ejecutar=ejecutar,
            llamadas_a_emitir=self.llamadas_a_emitir,
        )
        self.sesiones_abiertas.append(sesion)
        return sesion

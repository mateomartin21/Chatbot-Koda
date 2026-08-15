"""La herramienta que cierra el circulo: lo que el modelo lee del reloj marca la
sesion como hecha, pero NO toca los calculos del plan."""

from datetime import date

import pytest

from app.application.coach import ejecutor_para
from app.application.contexto import ReposDelCoach
from app.application.planes import DatosDelPlan, crear_plan
from app.domain.models import DatosPerfil, Runner
from app.domain.ports.llm_port import LlamadaHerramienta
from tests.fakes.repos import (
    InMemoryConversacionRepo,
    InMemoryMemoriaRepo,
    InMemoryPlanRepo,
    InMemoryRunnerRepo,
)

HOY = date(2026, 8, 14)


async def _con_plan() -> tuple[Runner, ReposDelCoach]:
    runners = InMemoryRunnerRepo()
    runner = await runners.crear_o_actualizar_acceso("mateo@ejemplo.com")
    await runners.actualizar_perfil(
        runner.id,
        DatosPerfil(nivel="intermedio", dias_disponibles=4, marca_distancia_km=10, marca_tiempo_seg=3150),
    )
    repos = ReposDelCoach(
        runners=runners,
        planes=InMemoryPlanRepo(),
        conversaciones=InMemoryConversacionRepo(),
        memoria=InMemoryMemoriaRepo(),
    )
    await crear_plan(
        runner=await runners.obtener(runner.id),
        datos=DatosDelPlan(distancia_km=21.1, fecha_carrera=date(2026, 11, 8)),
        runners=runners,
        planes=repos.planes,
        hoy=HOY,
    )
    return runner, repos


@pytest.mark.asyncio
async def test_registrar_marca_la_sesion_de_ese_dia_como_hecha() -> None:
    runner, repos = await _con_plan()
    activo = await repos.planes.obtener_activo(runner.id)
    sesion = next(s for s in activo.sesiones_programadas() if s.fecha >= HOY)

    ejecutar = ejecutor_para(runner, repos, hoy=sesion.fecha)
    respuesta = await ejecutar(
        LlamadaHerramienta(
            nombre="registrar_entrenamiento",
            argumentos={"distancia_km": 8.2, "duracion_min": 47},
        )
    )

    assert "hecha" in respuesta.lower()
    despues = await repos.planes.obtener_activo(runner.id)
    marcada = next(s for s in despues.sesiones_programadas() if s.fecha == sesion.fecha)
    assert marcada.completada


@pytest.mark.asyncio
async def test_la_proxima_sesion_avanza_despues_de_registrar() -> None:
    """Si registrar no moviera la proxima sesion, Koda seguiria diciendo 'hoy te toca'
    justo despues de que el runner le haya dicho que ya salio."""
    runner, repos = await _con_plan()
    activo = await repos.planes.obtener_activo(runner.id)
    primera = next(s for s in activo.sesiones_programadas() if s.fecha >= HOY)

    ejecutar = ejecutor_para(runner, repos, hoy=primera.fecha)
    await ejecutar(LlamadaHerramienta(nombre="registrar_entrenamiento", argumentos={"distancia_km": 8.2}))

    siguiente = await repos.planes.proxima_sesion(runner.id, primera.fecha)
    assert siguiente is None or siguiente.fecha > primera.fecha


@pytest.mark.asyncio
async def test_un_dia_sin_sesion_se_apunta_pero_no_marca_nada() -> None:
    runner, repos = await _con_plan()

    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    respuesta = await ejecutar(
        LlamadaHerramienta(
            nombre="registrar_entrenamiento",
            argumentos={"distancia_km": 5, "dia": 1, "mes": 1},
        )
    )

    assert "no le tocaba" in respuesta
    # Y aun asi le pide al coach que repita los numeros: es la unica forma de que el
    # runner detecte que el modelo leyo mal la pantalla.
    assert "repitele" in respuesta.lower()


@pytest.mark.asyncio
async def test_lo_leido_en_la_foto_no_cambia_los_ritmos_del_runner() -> None:
    """El dominio calcula con la marca que el runner confirmo, no con lo que un
    modelo creyo ver en la pantalla de un reloj."""
    runner, repos = await _con_plan()
    antes = await repos.runners.obtener(runner.id)

    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    await ejecutar(
        LlamadaHerramienta(
            nombre="registrar_entrenamiento",
            argumentos={"distancia_km": 10, "duracion_min": 31},  # un 10K en 31 min
        )
    )

    despues = await repos.runners.obtener(runner.id)
    assert despues.marca_distancia_km == antes.marca_distancia_km
    assert despues.marca_tiempo_seg == antes.marca_tiempo_seg


@pytest.mark.asyncio
async def test_el_entrenamiento_queda_en_la_memoria_duradera() -> None:
    runner, repos = await _con_plan()

    ejecutar = ejecutor_para(runner, repos, hoy=HOY)
    await ejecutar(
        LlamadaHerramienta(
            nombre="registrar_entrenamiento",
            argumentos={"distancia_km": 12, "sensacion": "me costó el final"},
        )
    )

    hechos = await repos.memoria.vigentes(runner.id)
    assert any("12 km" in h.hecho and "me costó el final" in h.hecho for h in hechos)

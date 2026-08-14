"""Los seis tests de docs/contexto/02-DOMINIO-RUNNING.md §5, escritos ANTES del codigo.

No prueban getters: prueban que el sistema entiende de running. Si alguno se pone en
rojo, es que el plan que Koda entregaria es malo para las piernas de alguien.
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.models import Runner
from app.domain.training.factory import estrategia_para
from app.domain.training.modelos import (
    Distancia,
    Nivel,
    Objetivo,
    PlanEntrenamiento,
    PlanNoViable,
    TipoSesion,
)
from app.domain.training.paces import predecir_tiempo

HOY = date(2026, 8, 13)


def _runner(nivel: Nivel = Nivel.INTERMEDIO, dias: int = 4) -> Runner:
    return Runner(
        id=uuid4(),
        email="corredor@example.com",
        creado_en=datetime(2026, 1, 1),
        nivel=nivel.value,
        dias_disponibles=dias,
        marca_distancia_km=5,
        marca_tiempo_seg=25 * 60,
    )


def _objetivo(distancia: Distancia, semanas: int) -> Objetivo:
    return Objetivo(distancia=distancia, fecha_carrera=HOY + timedelta(weeks=semanas))


def _volumen_por_semana(plan: PlanEntrenamiento) -> list[float]:
    return [s.volumen_km for s in plan.semanas]


def _plan(distancia: Distancia, semanas: int, runner: Runner) -> PlanEntrenamiento:
    """hoy se pasa siempre fijo: un test no puede depender de la fecha real."""
    return estrategia_para(distancia).generar(runner, _objetivo(distancia, semanas), hoy=HOY)


def test_riegel_predice_10k_desde_5k():
    t = predecir_tiempo(t1_seg=25 * 60, d1_km=5, d2_km=10)
    assert 51 * 60 < t < 53 * 60  # ~52 min, coherente con la formula


def test_maraton_en_seis_semanas_es_rechazado():
    """R6, la regla estrella: el sistema se niega y propone una alternativa concreta."""
    with pytest.raises(PlanNoViable) as e:
        _plan(Distancia.K42, semanas=6, runner=_runner(Nivel.PRINCIPIANTE))
    assert e.value.alternativa.distancia == Distancia.K21


def test_el_volumen_nunca_sube_mas_del_diez_por_ciento():
    """R1: progresion del 10%."""
    plan = _plan(Distancia.K10, semanas=12, runner=_runner())
    volumenes = _volumen_por_semana(plan)
    for previa, actual in zip(volumenes, volumenes[1:], strict=False):
        assert actual <= previa * 1.10 + 0.01


def test_hay_semana_de_descarga_cada_cuatro():
    """R3: cada 3-4 semanas se recorta el volumen para asimilar la carga."""
    plan = _plan(Distancia.K21, semanas=16, runner=_runner())
    assert any(s.es_descarga for s in plan.semanas[3:5])


def test_el_taper_reduce_volumen_antes_de_la_carrera():
    """R4: tapering — se baja el volumen manteniendo algo de intensidad."""
    plan = _plan(Distancia.K42, semanas=20, runner=_runner(Nivel.AVANZADO))
    volumenes = _volumen_por_semana(plan)
    assert volumenes[-1] < volumenes[-4] * 0.6


@pytest.mark.parametrize("nivel", list(Nivel))
@pytest.mark.parametrize("dias", [3, 4, 5, 6])
@pytest.mark.parametrize(
    ("distancia", "semanas"),
    [(Distancia.K5, 8), (Distancia.K10, 12), (Distancia.K21, 16), (Distancia.K42, 20)],
)
def test_ninguna_sesion_se_come_la_semana(distancia: Distancia, semanas: int, dias: int, nivel: Nivel):
    """R8 en todas las combinaciones, no solo en la que miraban los seis tests del spec.

    Sin esto pasaba desapercibido que, con 4 dias y dos sesiones de calidad, el unico
    dia facil se quedaba el 48% del volumen: un rodaje mas largo que la tirada larga.
    """
    plan = _plan(distancia, semanas=semanas, runner=_runner(nivel, dias=dias))
    for semana in plan.semanas:
        dias_corriendo = sum(1 for s in semana.sesiones if s.tipo != TipoSesion.DESCANSO)
        tope = 0.45 if dias_corriendo <= 3 else 0.35
        mas_larga = max(s.distancia_km for s in semana.sesiones)
        assert mas_larga <= semana.volumen_km * tope + 0.05, (
            f"semana {semana.numero}: una sesion de {mas_larga} km sobre {semana.volumen_km} km"
        )
        # La tirada larga tiene que ser la sesion mas larga; si no, algo se desbordo.
        larga = next(s for s in semana.sesiones if s.tipo == TipoSesion.LARGO)
        assert larga.distancia_km == mas_larga


@pytest.mark.parametrize("dias", [3, 4, 5, 6])
def test_la_intensidad_ronda_el_veinte_por_ciento(dias: int):
    """R2: polarizacion 80/20 — el trabajo duro no puede desbordarse."""
    plan = _plan(Distancia.K10, semanas=12, runner=_runner(dias=dias))
    for semana in plan.semanas:
        duro = sum(s.distancia_km for s in semana.sesiones if s.tipo in (TipoSesion.SERIES, TipoSesion.TEMPO))
        assert duro <= semana.volumen_km * 0.22


def test_ningun_principiante_corre_siete_dias():
    """R7: siempre queda al menos un dia de descanso."""
    plan = _plan(Distancia.K5, semanas=8, runner=_runner(Nivel.PRINCIPIANTE, dias=7))
    for semana in plan.semanas:
        assert sum(1 for s in semana.sesiones if s.tipo != TipoSesion.DESCANSO) <= 4

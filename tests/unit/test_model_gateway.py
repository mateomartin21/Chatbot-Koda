"""Gateway de modelos: cadena ordenada de proveedores, no un reintento de la misma
llamada — ver docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md."""

import pytest

from app.infrastructure.llm.model_gateway import ModelGatewayLLM
from tests.fakes.pipeline_voz import FakeLLM

SYSTEM_PROMPT = "eres koda"


async def test_usa_el_primer_tier_si_responde():
    tier1 = FakeLLM(respuesta="respuesta de sonnet")
    tier2 = FakeLLM(respuesta="respuesta de groq")
    gateway = ModelGatewayLLM([tier1, tier2])

    respuesta = await gateway.conversar("hola", system_prompt=SYSTEM_PROMPT)

    assert respuesta == "respuesta de sonnet"
    assert tier2.mensajes_recibidos == []  # nunca se llamo, el primero ya respondio


async def test_cae_al_segundo_tier_si_el_primero_falla():
    tier1 = FakeLLM()
    tier1.falla = True
    tier2 = FakeLLM(respuesta="respuesta del segundo proveedor")
    gateway = ModelGatewayLLM([tier1, tier2])

    respuesta = await gateway.conversar("hola", system_prompt=SYSTEM_PROMPT)

    assert respuesta == "respuesta del segundo proveedor"
    assert tier1.mensajes_recibidos == ["hola"]
    assert tier2.mensajes_recibidos == ["hola"]


async def test_cae_al_segundo_tier_si_el_primero_se_pasa_del_timeout():
    tier1 = FakeLLM()
    tier1.retraso_segundos = 0.2
    tier2 = FakeLLM(respuesta="respuesta rapida")
    gateway = ModelGatewayLLM([tier1, tier2], timeout_segundos=0.05)

    respuesta = await gateway.conversar("hola", system_prompt=SYSTEM_PROMPT)

    assert respuesta == "respuesta rapida"


async def test_propaga_el_error_si_todos_los_tiers_fallan():
    tier1, tier2 = FakeLLM(), FakeLLM()
    tier1.falla = True
    tier2.falla = True
    gateway = ModelGatewayLLM([tier1, tier2])

    with pytest.raises(RuntimeError, match="LLM no disponible"):
        await gateway.conversar("hola", system_prompt=SYSTEM_PROMPT)


def test_no_acepta_una_lista_vacia_de_tiers():
    with pytest.raises(ValueError, match="al menos un tier"):
        ModelGatewayLLM([])

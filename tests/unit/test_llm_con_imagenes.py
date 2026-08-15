"""Un modelo que no ve no puede contestar sobre una foto.

Es el fallo silencioso de esta funcion: el modelo ciego recibe el texto que
acompana a la imagen ("registra esto") y contesta como si la hubiera mirado. El
runner se cree que su entrenamiento quedo apuntado y no lo esta. Antes ninguna
respuesta que una inventada.
"""

import pytest

from app.application.procesar_mensaje import procesar_mensaje
from app.domain.ports.llm_port import Imagen
from app.infrastructure.llm.model_gateway import ModelGatewayLLM
from tests.fakes.pipeline_voz import FakeLLM, FakeSTT, FakeTTS

FOTO = Imagen(datos=b"jpeg-falso", formato="jpeg")


@pytest.mark.asyncio
async def test_el_gateway_se_salta_los_modelos_que_no_ven() -> None:
    ciego = FakeLLM("no vi nada pero contesto igual", con_imagenes=False)
    vidente = FakeLLM("veo 8 km en 47 minutos", con_imagenes=True)
    gateway = ModelGatewayLLM([ciego, vidente])

    respuesta = await gateway.conversar("¿qué ves?", system_prompt="eres koda", imagen=FOTO)

    assert respuesta == "veo 8 km en 47 minutos"
    assert ciego.mensajes_recibidos == [], "la foto llego a un modelo que no sabe verla"
    assert vidente.imagenes_recibidas == [FOTO]


@pytest.mark.asyncio
async def test_sin_foto_el_orden_de_los_tiers_no_cambia() -> None:
    """El filtro por vision solo aplica cuando hay imagen: en una conversacion normal
    el tier barato sigue siendo el primero."""
    primero = FakeLLM("contesto yo", con_imagenes=False)
    segundo = FakeLLM("no me toca", con_imagenes=True)
    gateway = ModelGatewayLLM([primero, segundo])

    assert await gateway.conversar("hola", system_prompt="eres koda") == "contesto yo"
    assert segundo.mensajes_recibidos == []


@pytest.mark.asyncio
async def test_si_ningun_modelo_ve_se_dice_en_vez_de_inventar() -> None:
    ciego = FakeLLM("aqui va una respuesta inventada", con_imagenes=False)

    respuesta = await procesar_mensaje(
        texto=None,
        audio=None,
        audio_mime=None,
        stt=FakeSTT(),
        llm=ModelGatewayLLM([ciego]),
        tts=FakeTTS(),
        system_prompt="eres koda",
        imagen=FOTO,
    )

    assert "no puedo mirar fotos" in respuesta.texto
    assert ciego.mensajes_recibidos == []


@pytest.mark.asyncio
async def test_la_foto_llega_al_modelo_junto_al_texto_del_runner() -> None:
    vidente = FakeLLM("son 8 km", con_imagenes=True)

    respuesta = await procesar_mensaje(
        texto="¿qué tal me quedó?",
        audio=None,
        audio_mime=None,
        stt=FakeSTT(),
        llm=vidente,
        tts=FakeTTS(),
        system_prompt="eres koda",
        imagen=FOTO,
    )

    assert respuesta.texto == "son 8 km"
    assert vidente.mensajes_recibidos == ["¿qué tal me quedó?"]
    assert vidente.imagenes_recibidas == [FOTO]


@pytest.mark.asyncio
async def test_una_foto_sin_texto_sigue_siendo_un_turno_completo() -> None:
    """Mandar solo la foto es una peticion valida: "mira esto"."""
    vidente = FakeLLM("veo tu reloj", con_imagenes=True)

    respuesta = await procesar_mensaje(
        texto=None,
        audio=None,
        audio_mime=None,
        stt=FakeSTT(),
        llm=vidente,
        tts=FakeTTS(),
        system_prompt="eres koda",
        imagen=FOTO,
    )

    assert respuesta.texto == "veo tu reloj"
    assert vidente.mensajes_recibidos and vidente.mensajes_recibidos[0].strip()

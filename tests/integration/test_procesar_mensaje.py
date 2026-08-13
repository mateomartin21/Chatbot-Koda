"""Caso de uso con adaptadores falsos — ver docs/contexto/08-CONVENCIONES.md."""

from app.application.procesar_mensaje import procesar_mensaje
from tests.fakes.pipeline_voz import FakeLLM, FakeSTT, FakeTTS

SYSTEM_PROMPT = "eres koda"


async def test_procesa_un_mensaje_de_texto_sin_pasar_por_stt():
    stt, llm, tts = FakeSTT(), FakeLLM(respuesta="hola humano"), FakeTTS()

    respuesta = await procesar_mensaje(
        texto="hola koda", audio=None, audio_mime=None, stt=stt, llm=llm, tts=tts, system_prompt=SYSTEM_PROMPT
    )

    assert respuesta.texto == "hola humano"
    assert respuesta.audio == b"audio-falso"
    assert llm.mensajes_recibidos == ["hola koda"]


async def test_procesa_un_mensaje_de_voz_transcribiendolo_primero():
    stt = FakeSTT(transcripcion="quiero correr un 10k")
    llm = FakeLLM(respuesta="genial, hablemos de tu 10k")
    tts = FakeTTS()

    respuesta = await procesar_mensaje(
        texto=None,
        audio=b"bytes-de-audio",
        audio_mime="audio/webm",
        stt=stt,
        llm=llm,
        tts=tts,
        system_prompt=SYSTEM_PROMPT,
    )

    assert respuesta.texto == "genial, hablemos de tu 10k"
    assert llm.mensajes_recibidos == ["quiero correr un 10k"]


async def test_si_stt_falla_responde_con_elegancia_sin_llamar_al_llm():
    stt, llm, tts = FakeSTT(), FakeLLM(), FakeTTS()
    stt.falla = True

    respuesta = await procesar_mensaje(
        texto=None,
        audio=b"bytes",
        audio_mime="audio/webm",
        stt=stt,
        llm=llm,
        tts=tts,
        system_prompt=SYSTEM_PROMPT,
    )

    assert "repites" in respuesta.texto.lower()
    assert respuesta.audio is None
    assert llm.mensajes_recibidos == []


async def test_si_tts_falla_la_respuesta_sigue_solo_en_texto():
    stt, llm, tts = FakeSTT(), FakeLLM(respuesta="aqui tienes"), FakeTTS()
    tts.falla = True

    respuesta = await procesar_mensaje(
        texto="hola", audio=None, audio_mime=None, stt=stt, llm=llm, tts=tts, system_prompt=SYSTEM_PROMPT
    )

    assert respuesta.texto == "aqui tienes"
    assert respuesta.audio is None


async def test_si_el_llm_falla_dos_veces_responde_con_mensaje_amable():
    stt, llm, tts = FakeSTT(), FakeLLM(), FakeTTS()
    llm.falla = True

    respuesta = await procesar_mensaje(
        texto="hola", audio=None, audio_mime=None, stt=stt, llm=llm, tts=tts, system_prompt=SYSTEM_PROMPT
    )

    assert "complic" in respuesta.texto.lower()
    assert respuesta.audio == b"audio-falso"  # Polly (aqui, el fake) sigue funcionando

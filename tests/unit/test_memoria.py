"""Capa 3: extraer de la conversacion lo que trasciende la sesion.

Lo que se prueba no es que un modelo extraiga bien — eso no es determinista y no se
puede testear sin red. Se prueba lo otro: que cuando el modelo devuelva basura, y lo
va a hacer, no acabe en la memoria del runner. Una memoria vacia es mejor que una
memoria corrupta, porque lo segundo se le cuenta como si fuera verdad.
"""

from uuid import uuid4

import pytest

from app.application.memoria import extraer_y_guardar, parsear_hechos
from app.domain.models import Mensaje
from tests.fakes.pipeline_voz import FakeLLM
from tests.fakes.repos import InMemoryMemoriaRepo

PROMPT = "extrae hechos"
CONVERSACION = [
    Mensaje(rol="usuario", contenido="me duele la rodilla derecha cuando bajo cuestas"),
    Mensaje(rol="coach", contenido="entendido, lo tomamos en cuenta"),
]


@pytest.fixture
def memoria() -> InMemoryMemoriaRepo:
    return InMemoryMemoriaRepo()


def test_un_json_limpio_se_convierte_en_hechos():
    hechos = parsear_hechos('[{"categoria": "lesion", "hecho": "rodilla derecha en bajadas"}]')

    assert len(hechos) == 1
    assert hechos[0].categoria == "lesion"


def test_el_json_envuelto_en_markdown_tambien_vale():
    """Los modelos pequenos casi siempre lo envuelven, por mucho que el prompt lo prohiba."""
    respuesta = 'Aqui tienes:\n```json\n[{"categoria": "logro", "hecho": "termino su primer 5K"}]\n```'
    assert len(parsear_hechos(respuesta)) == 1


@pytest.mark.parametrize(
    "respuesta",
    [
        "no he encontrado nada relevante",  # prosa en vez de JSON
        "[]",
        "{}",
        '[{"hecho": "sin categoria"}]',
        '[{"categoria": "chisme", "hecho": "le cae mal su vecino"}]',  # categoria inventada
        '[{"categoria": "lesion", "hecho": "x"}]',  # demasiado corto para ser util
        '[{"categoria": "lesion", "hecho": "rodilla", "confianza": 0.2}]',  # esta adivinando
    ],
)
def test_lo_que_no_es_valido_no_llega_a_la_memoria(respuesta: str):
    assert parsear_hechos(respuesta) == []


def test_un_hecho_malo_no_arrastra_a_los_buenos():
    respuesta = """[
        {"categoria": "inventada", "hecho": "esto no vale"},
        {"categoria": "preferencia", "hecho": "prefiere correr por la manana"}
    ]"""
    hechos = parsear_hechos(respuesta)

    assert [h.categoria for h in hechos] == ["preferencia"]


def test_no_se_guardan_mas_de_cinco_por_turno():
    """Un modelo que se emociona puede devolver veinte hechos de una charla trivial."""
    respuesta = (
        "[" + ",".join(f'{{"categoria":"contexto","hecho":"dato numero {i}"}}' for i in range(20)) + "]"
    )
    assert len(parsear_hechos(respuesta)) == 5


async def test_la_extraccion_guarda_lo_que_encuentra(memoria):
    llm = FakeLLM(respuesta='[{"categoria": "lesion", "hecho": "rodilla derecha en bajadas"}]')
    runner_id = uuid4()

    guardados = await extraer_y_guardar(runner_id, CONVERSACION, memoria, llm, PROMPT)

    assert guardados == 1
    assert (await memoria.vigentes(runner_id))[0].categoria == "lesion"


async def test_solo_se_le_pasa_la_conversacion_al_modelo(memoria):
    llm = FakeLLM(respuesta="[]")
    await extraer_y_guardar(uuid4(), CONVERSACION, memoria, llm, PROMPT)

    enviado = llm.mensajes_recibidos[0]
    assert "me duele la rodilla" in enviado
    assert llm.prompts_recibidos[0] == PROMPT


@pytest.mark.parametrize("cortesia", ["hola", "Gracias!", "ok", "  Buenos dias  ", "sí"])
async def test_una_cortesia_no_gasta_una_llamada_al_modelo(memoria, cortesia: str):
    """La extraccion cuesta dinero en cada turno. Un saludo no trae nada que recordar."""
    llm = FakeLLM(respuesta="[]")

    guardados = await extraer_y_guardar(
        uuid4(), [Mensaje(rol="usuario", contenido=cortesia)], memoria, llm, PROMPT
    )

    assert guardados == 0
    assert llm.mensajes_recibidos == []  # ni se llamo


@pytest.mark.parametrize("mensaje", ["la rodilla", "vivo en CDMX", "me duele"])
async def test_un_mensaje_corto_con_contenido_si_se_extrae(memoria, mensaje: str):
    """Este filtro era un minimo de caracteres y descartaba "la rodilla": diez letras y
    justo el dato que habia que recordar. La longitud no mide contenido."""
    llm = FakeLLM(respuesta="[]")

    await extraer_y_guardar(uuid4(), [Mensaje(rol="usuario", contenido=mensaje)], memoria, llm, PROMPT)

    assert llm.mensajes_recibidos != []  # si se llamo


async def test_si_el_modelo_falla_la_conversacion_no_se_entera(memoria):
    """Es trabajo de fondo: si revienta se pierde un hecho, nunca una respuesta."""
    llm = FakeLLM()
    llm.falla = True

    assert await extraer_y_guardar(uuid4(), CONVERSACION, memoria, llm, PROMPT) == 0


async def test_lo_que_ya_se_sabia_no_se_guarda_otra_vez(memoria):
    llm = FakeLLM(respuesta='[{"categoria": "preferencia", "hecho": "Prefiere correr por la mañana."}]')
    runner_id = uuid4()

    primera = await extraer_y_guardar(runner_id, CONVERSACION, memoria, llm, PROMPT)
    segunda = await extraer_y_guardar(runner_id, CONVERSACION, memoria, llm, PROMPT)

    assert (primera, segunda) == (1, 0)
    assert len(await memoria.vigentes(runner_id)) == 1

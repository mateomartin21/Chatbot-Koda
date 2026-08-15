"""Los prompts son codigo: se despliegan, cambian el comportamiento y se rompen.

Lo que se prueba aqui no es que esten "bien escritos" — eso no lo sabe un test — sino
que no se hayan quedado desincronizados de lo que la aplicacion sabe hacer de verdad.

Es un fallo que ya paso, y caro: `coach_system.md` seguia diciendo que Koda todavia
NO tenia memoria entre sesiones, ni registro de entrenamientos, ni lectura de fotos.
Las tres llevaban dias funcionando. El modelo hacia caso al prompt y se disculpaba por
cosas que sabia hacer.
"""

from pathlib import Path

import pytest

from app.application.coach import HERRAMIENTAS, HERRAMIENTAS_VOZ

PROMPTS = Path(__file__).resolve().parents[2] / "app" / "prompts"


def _texto(nombre: str) -> str:
    return (PROMPTS / nombre).read_text(encoding="utf-8")


@pytest.mark.parametrize("prompt", ["coach_system.md", "coach_voz.md"])
def test_el_prompt_del_coach_nombra_todas_sus_herramientas(prompt: str) -> None:
    """Una herramienta que existe pero no esta en el prompt es una herramienta que el
    modelo no va a usar nunca. Es la forma silenciosa de perder una funcion entera."""
    texto = _texto(prompt)
    faltan = [h.nombre for h in HERRAMIENTAS if h.nombre not in texto]
    assert not faltan, f"{prompt} no menciona: {faltan}"


@pytest.mark.parametrize("prompt", ["coach_system.md", "coach_voz.md"])
def test_el_prompt_del_coach_no_nombra_herramientas_que_no_existen(prompt: str) -> None:
    """Y al reves: prometerle al modelo una herramienta retirada le hace intentar
    llamarla, gastar un turno y contestar con un error."""
    texto = _texto(prompt)
    nombres = {h.nombre for h in HERRAMIENTAS}
    inventadas = [
        palabra
        for palabra in ("crear_entrenamiento", "plan_de_gimnasio", "buscar_carrera")
        if palabra in texto and palabra not in nombres
    ]
    assert not inventadas, f"{prompt} promete herramientas que no existen: {inventadas}"


def test_el_prompt_de_la_voz_no_conoce_ninguna_herramienta_del_dominio() -> None:
    """La voz no decide (ADR-020). Si su prompt nombrara `crear_plan`, tarde o
    temprano intentaria llamarla — y no la tiene."""
    texto = _texto("voz_locutor.md")

    for herramienta in HERRAMIENTAS:
        assert herramienta.nombre not in texto, herramienta.nombre
    # La unica que si conoce, y por su nombre exacto.
    (puente,) = HERRAMIENTAS_VOZ
    assert puente.nombre in texto


def test_el_coach_sabe_donde_acaba_lo_que_puede_hacer() -> None:
    """Sin este limite escrito, el modelo improvisa una entrevista para una funcion
    que no existe: pregunta cuantos dias de gimnasio, se los dicen, pregunta que tipo,
    se lo dicen, y no llega a ningun sitio porque no hay herramienta que lo construya.
    Se vio en una conversacion real y no paraba nunca."""
    for prompt in ("coach_system.md", "coach_voz.md"):
        texto = _texto(prompt).lower()
        assert "gimnasio" in texto, prompt
        assert "si no hay" in texto and "no preguntes" in texto, prompt

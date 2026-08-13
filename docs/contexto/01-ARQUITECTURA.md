# 01 · Arquitectura

## La regla que nunca se rompe

> **Las dependencias apuntan hacia adentro.**
> `interfaces` → `application` → `domain` ← `infrastructure`
>
> `infrastructure` conoce a `domain`. **`domain` no sabe que existe `infrastructure`.**

Si abres cualquier archivo de `app/domain/` y encuentras `import boto3`, `import sqlalchemy` o `import fastapi`, está mal. Hay un test que lo comprueba automáticamente (ver abajo).

---

## Por qué hexagonal aquí, y no porque suene bien

Este proyecto tiene **cuatro dependencias externas volátiles**: Transcribe, Bedrock, Polly y SES. Los modelos de IA se renombran, se deprecan y cambian de precio cada pocos meses. Si el dominio importa `boto3`, cada cambio de proveedor obliga a tocar las reglas de entrenamiento — que no tienen nada que ver.

Con puertos y adaptadores el dominio declara *"necesito algo que convierta audio en texto"* (`STTPort`) y se acaba la conversación. Que sea Transcribe, Whisper o Deepgram es un detalle de infraestructura.

**Dos beneficios que se sienten esta misma semana:**

1. **Los tests corren sin internet y sin gastar créditos.** Con `FakeSTT`, `FakeLLM` y `FakeTTS` la suite entera tarda segundos y cuesta cero. Sin esto, cada test cuesta dinero.
2. **La arquitectura es el plan B.** Si AWS falla, se cambian tres líneas en `container.py` (ver §00). Eso no es teoría: es la mitigación real del riesgo principal del proyecto.

Ver [ADR-003](../adr/ADR-003-arquitectura-hexagonal.md).

---

## Estructura de carpetas

```
koda-running-coach/
├── app/
│   ├── domain/                     # ❤️ CERO imports de librerías externas
│   │   ├── models.py               # Runner, Objetivo, PlanEntrenamiento, Sesion, Registro
│   │   ├── value_objects.py        # Distancia, Ritmo, Nivel, TipoSesion
│   │   ├── errors.py               # excepciones del dominio
│   │   ├── training/
│   │   │   ├── strategy.py         # EstrategiaPlan (interfaz abstracta)
│   │   │   ├── plan_5k.py          # ┐
│   │   │   ├── plan_10k.py         # ├ Patrón Strategy — una por distancia
│   │   │   ├── plan_21k.py         # │
│   │   │   ├── plan_42k.py         # ┘
│   │   │   ├── factory.py          # elige la estrategia según la distancia
│   │   │   └── paces.py            # cálculo de ritmos (Riegel)
│   │   └── ports/
│   │       ├── stt_port.py
│   │       ├── tts_port.py
│   │       ├── llm_port.py
│   │       ├── vision_port.py      # análisis de imágenes y fotogramas
│   │       ├── email_port.py
│   │       ├── storage_port.py     # audio e imágenes subidas
│   │       └── repositories.py     # RunnerRepo, PlanRepo, ConversationRepo, MemoryRepo
│   │
│   ├── application/                # casos de uso: orquestan, no deciden reglas
│   │   ├── procesar_mensaje.py     # el caso de uso central (voz, texto, imagen, vídeo)
│   │   ├── generar_plan.py
│   │   ├── registrar_entrenamiento.py
│   │   ├── ajustar_plan.py
│   │   ├── enviar_correo_diario.py
│   │   ├── auth/
│   │   │   ├── solicitar_enlace.py
│   │   │   └── canjear_enlace.py
│   │   ├── contexto.py             # ensambla el contexto del LLM (¡scoped por runner!)
│   │   └── tools.py                # herramientas expuestas al LLM
│   │
│   ├── infrastructure/             # adaptadores: aquí sí viven boto3 y los SDKs
│   │   ├── stt/transcribe_aws.py
│   │   ├── stt/groq_whisper.py     # respaldo / comparativa de latencia
│   │   ├── llm/bedrock_converse.py
│   │   ├── tts/polly.py
│   │   ├── vision/bedrock_vision.py
│   │   ├── video/keyframes.py      # ffmpeg: vídeo → fotogramas
│   │   ├── email/ses.py
│   │   ├── email/plantillas/
│   │   ├── storage/s3.py
│   │   ├── persistence/
│   │   │   ├── orm.py              # modelos SQLAlchemy
│   │   │   └── repos.py            # repositorios concretos
│   │   └── scheduler/apscheduler_adapter.py
│   │
│   ├── interfaces/                 # puertas de entrada
│   │   ├── api/
│   │   │   ├── deps.py             # ⚠️ get_current_runner() vive aquí
│   │   │   ├── auth.py             # POST /api/auth/solicitar · GET /api/auth/canjear
│   │   │   ├── mensajes.py         # POST /api/mensajes   ← endpoint central
│   │   │   ├── planes.py           # GET  /api/plan
│   │   │   └── health.py
│   │   └── web/
│   │       ├── index.html
│   │       ├── app.js
│   │       └── styles.css
│   │
│   ├── prompts/                    # 📄 prompts como archivos versionados
│   ├── container.py                # composition root: el ÚNICO sitio que ensambla
│   └── config.py                   # pydantic-settings
│
├── tests/{unit,integration,security,fakes}/
├── docs/{contexto,adr,diagramas}/
├── alembic/
├── .env.example
├── requirements.txt
├── Dockerfile
├── .github/workflows/ci.yml
└── README.md
```

---

## Responsabilidad de cada capa

| Capa | Sí hace | No hace |
|---|---|---|
| **domain** | Reglas de entrenamiento, entidades, invariantes, definición de puertos | Llamar a nada externo. Saber que existe una base de datos |
| **application** | Orquestar pasos, transacciones, ensamblar contexto, aplicar autorización | Contener reglas de entrenamiento. Conocer SDKs concretos |
| **infrastructure** | Hablar con AWS, la BD, el sistema de ficheros | Contener lógica de negocio |
| **interfaces** | HTTP, validación de entrada, serialización, sesión del usuario | Contener lógica de negocio |

**El error más común** es meter reglas de negocio en `interfaces` porque "es más rápido". Si te descubres escribiendo `if distancia == 42 and semanas < 16` dentro de un endpoint de FastAPI, para y muévelo a `domain/training/`.

---

## El caso de uso central: `procesar_mensaje`

Todo el producto pasa por aquí. Una sola entrada, cuatro modalidades.

```python
@dataclass
class MensajeEntrante:
    runner_id: UUID            # ⚠️ SIEMPRE del JWT, JAMÁS del cuerpo de la petición
    texto: str | None = None
    audio: BinaryIO | None = None
    audio_mime: str | None = None
    imagenes: list[BinaryIO] = field(default_factory=list)
    video: BinaryIO | None = None

async def procesar_mensaje(msg: MensajeEntrante) -> RespuestaCoach:
    # 1. Normalizar entrada a texto + adjuntos visuales
    texto = msg.texto or await stt.transcribir(msg.audio, msg.audio_mime)
    visuales = await preparar_visuales(msg.imagenes, msg.video)

    # 2. Ensamblar contexto — SIEMPRE acotado a este runner
    contexto = await construir_contexto(msg.runner_id)

    # 3. Razonar, con herramientas del dominio
    respuesta = await llm.conversar(contexto, texto, visuales, tools=HERRAMIENTAS)

    # 4. Sintetizar voz
    audio = await tts.sintetizar(respuesta.texto)

    # 5. Persistir el turno y extraer hechos duraderos
    await guardar_turno(msg.runner_id, texto, respuesta)
    return RespuestaCoach(texto=respuesta.texto, audio=audio, plan=respuesta.plan)
```

Nota los dos comentarios de `runner_id`. Son el corazón de §03.

---

## Composition root

`container.py` es el **único** archivo del proyecto que sabe qué adaptador concreto se usa. Cambiar de proveedor se hace aquí y en ningún otro sitio.

```python
def build_container(settings: Settings) -> Container:
    stt = TranscribeAWS(settings) if settings.stt == "aws" else GroqWhisper(settings)
    llm = BedrockConverse(settings) if settings.llm == "aws" else GeminiLLM(settings)
    tts = PollyTTS(settings)       if settings.tts == "aws" else GeminiTTS(settings)
    email = SESEmail(settings)     if settings.email == "aws" else ResendEmail(settings)
    return Container(stt=stt, llm=llm, tts=tts, email=email, repos=SqlRepos(settings))
```

Ese `if` es todo el plan B del §00. Los tests inyectan `FakeSTT`, `FakeLLM`, `FakeTTS` por la misma puerta.

---

## Test que protege la arquitectura

```python
# tests/unit/test_arquitectura.py
from pathlib import Path

PROHIBIDOS = ("boto3", "sqlalchemy", "fastapi", "requests", "httpx", "groq", "google")

def test_el_dominio_no_depende_de_infraestructura():
    for archivo in Path("app/domain").rglob("*.py"):
        codigo = archivo.read_text(encoding="utf-8")
        for prohibido in PROHIBIDOS:
            assert f"import {prohibido}" not in codigo, (
                f"{archivo} viola la regla hexagonal: importa {prohibido}"
            )
```

Un test de 8 líneas que convierte una convención en una garantía. Ponlo en CI el día 1.

---

## Manejo de errores y degradación

Cada llamada externa puede fallar. Reglas fijas:

| Falla | Comportamiento |
|---|---|
| **STT** no entiende el audio | Responder *"No te escuché bien, ¿lo repites?"* — nunca un error 500 |
| **LLM** no responde | Reintentar una vez con backoff; luego mensaje amable y registrar el incidente |
| **TTS** falla | **Devolver la respuesta solo en texto.** La conversación no se rompe por no tener voz |
| **Email** rebota | Marcar el correo como no entregable y desactivar recordatorios de ese runner |
| **BD** caída | 503 con `Retry-After`. No inventar datos |

El principio: **degradar, no morir**. Que falte la voz es molesto; que la app se caiga es descalificante.

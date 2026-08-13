# 00 · Contexto del proyecto

> **Empieza por aquí.** Si eres una persona nueva (o una sesión nueva de un asistente de IA) abriendo este repo, este archivo te da todo el contexto en 5 minutos. Los demás documentos profundizan.

---

## Qué es Koda

**Koda** es una web app de voz, responsive para móvil, que funciona como **entrenador personal de running**. El usuario le habla por el micrófono del navegador y Koda le responde con voz, le genera planes de entrenamiento reales para 5K / 10K / 21K / 42K, recuerda sus conversaciones anteriores y le manda recordatorios por correo.

**Enunciado original del reto:**

> Un chatbot de voz conversacional que funcione como entrenador personal (coach) para runners de todos los niveles, ayudándolos a prepararse para carreras de 5k, 10k, 21k y maratón. El formato de entrega y las tecnologías son totalmente libres. Como puntos extra opcionales, se valora que el chatbot tenga memoria de conversaciones anteriores y que envíe recordatorios proactivos por WhatsApp, correo o Telegram.

| | |
|---|---|
| **Entrega** | Lunes 17 de agosto de 2026 |
| **Naturaleza** | Prueba técnica para un proceso de entrevista |
| **Criterio principal** | Buenas prácticas y decisiones defendibles, por encima de cantidad de features |
| **Canal** | Web app responsive (mobile-first) |
| **Recordatorios** | Correo electrónico (Amazon SES) |
| **Extras cubiertos** | Memoria de conversaciones ✅ · Recordatorios proactivos ✅ |

---

## La tesis del proyecto (léela dos veces)

> **El LLM es la interfaz conversacional, no la fuente de verdad.**

Un chatbot mediocre le pide al modelo *"genera un plan de 10K"* y publica lo que salga. Koda **codifica el conocimiento de entrenamiento en el dominio, de forma determinista y testeada** (regla del 10 %, polarización 80/20, semanas de descarga, tapering, ritmos derivados), y usa el LLM únicamente para entender la intención del usuario y explicar el resultado.

Todo lo demás en este repo es consecuencia de esa frase. Si alguna vez dudas de una decisión de diseño, vuelve aquí.

---

## Estado y evolución del plan

La planificación pasó por tres versiones. Se documenta porque **la evolución del criterio es parte de lo que se evalúa**.

| Versión | Fecha | Qué decidió |
|---|---|---|
| **v1** | 13 ago | Telegram como canal, Groq Whisper (STT) + Google Gemini (LLM/TTS), recordatorios por Telegram |
| **v2** | 13 ago | Se descarta Telegram → **web app responsive móvil**. Se migra a **AWS** (Transcribe · Bedrock · Polly · SES). Recordatorios **solo por correo** |
| **v3** | 13 ago | Se añade **multiusuario con autenticación y aislamiento estricto de memoria** (§03) y **entradas multimodales**: texto, fotos y vídeo (§04) |

**Estos documentos `docs/` son ahora la fuente de verdad.** El plan maestro original queda como registro histórico.

### Por qué se añadió multiusuario (v3)

Sin autenticación, la memoria a largo plazo es global: los hechos de un runner (*"le duele la rodilla derecha"*) contaminarían las conversaciones de cualquier otro. Eso no es un bug de comodidad, **es una fuga de datos personales**. La corrección está en §03 y es probablemente la sección más valiosa del repo de cara a una entrevista.

---

## Mapa de la documentación

| Documento | Qué responde |
|---|---|
| **00-CONTEXTO** (este) | Qué es, en qué estado está, cómo está organizado |
| [01-ARQUITECTURA](01-ARQUITECTURA.md) | Cómo está estructurado el código y por qué hexagonal |
| [02-DOMINIO-RUNNING](02-DOMINIO-RUNNING.md) | Las reglas de entrenamiento y el modelo de datos |
| [03-MULTIUSUARIO-Y-SEGURIDAD](03-MULTIUSUARIO-Y-SEGURIDAD.md) | Autenticación y aislamiento entre usuarios |
| [04-ENTRADAS-MULTIMODALES](04-ENTRADAS-MULTIMODALES.md) | Voz, texto, fotos y vídeo |
| [05-MEMORIA](05-MEMORIA.md) | Cómo recuerda Koda sin reventar el contexto |
| [06-PROMPTS](06-PROMPTS.md) | Los prompts reales y las herramientas del LLM |
| [07-PLAN-EJECUCION](07-PLAN-EJECUCION.md) | Qué se hace cada día hasta el 17 |
| [08-CONVENCIONES](08-CONVENCIONES.md) | Git, código, tests, nombres |
| [../adr/](../adr/) | Las 8 decisiones de arquitectura con sus alternativas |

---

## Stack en una tabla

| Capa | Elección |
|---|---|
| Lenguaje | Python 3.12 |
| API | FastAPI + Uvicorn |
| Frontend | HTML + CSS + JS vanilla, mobile-first, sin build |
| STT (escuchar) | Amazon Transcribe (`es-MX`) |
| Cerebro | Amazon Bedrock — Converse API + tool use |
| TTS (hablar) | Amazon Polly (`es-MX`, motor generativo) |
| Correo | Amazon SES v2 |
| Auth | Enlace mágico por correo + JWT en cookie `httpOnly` |
| Datos | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Recordatorios | APScheduler con jobstore en PostgreSQL |
| Tests | pytest + dobles de prueba |
| CI | GitHub Actions |

---

## ⚠️ Plan B documentado

Al 13 de agosto **no existía todavía una cuenta de AWS**, y eso es el riesgo bloqueante del proyecto. Si AWS no se desbloquea a tiempo, se cambian **tres adaptadores** y nada más:

| Puerto | Plan A (AWS) | Plan B |
|---|---|---|
| `STTPort` | Amazon Transcribe | Groq Whisper |
| `LLMPort` | Amazon Bedrock | Google Gemini |
| `TTSPort` | Amazon Polly | Gemini TTS |
| `EmailPort` | Amazon SES | Resend |

**El dominio, la memoria, la autenticación, la web y el scheduler no se tocan.** Que este plan B cueste una tarde en lugar de una semana *es* el argumento a favor de la arquitectura hexagonal — ver [ADR-003](../adr/ADR-003-arquitectura-hexagonal.md).

---

## Glosario

| Término | Significado |
|---|---|
| **STT** | *Speech to Text* — convertir audio en texto |
| **TTS** | *Text to Speech* — convertir texto en audio |
| **Pipeline en cascada** | STT → LLM → TTS encadenados, frente a un modelo speech-to-speech |
| **Puerto** | Interfaz que el dominio exige (ej. `STTPort`) |
| **Adaptador** | Implementación concreta de un puerto (ej. `TranscribeAWS`) |
| **Tool use** | Capacidad del LLM de llamar funciones tuyas en lugar de inventar datos |
| **Runner** | El usuario de la app. Es la raíz de agregación y la frontera de aislamiento |
| **Tapering** | Reducción de volumen en las últimas semanas antes de una carrera |
| **Ritmo** | Minutos por kilómetro (min/km) |
| **Rodaje fácil** | Carrera a baja intensidad, base del entrenamiento |
| **Series** | Repeticiones a alta intensidad con recuperación entre ellas |
| **Tirada larga** | La sesión más larga de la semana, clave en 21K y 42K |

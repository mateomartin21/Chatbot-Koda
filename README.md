# 🐺 Koda Running Coach

> Entrenador personal de running conversacional por voz. Le hablas desde el móvil, te genera un plan real para tu carrera, se acuerda de lo que le cuentas y te escribe cada mañana.

<!-- TODO: sustituir por una captura real o un GIF de la app en el móvil -->

**🔗 Demo:** _(pendiente de desplegar)_ · **🎥 Vídeo:** _(pendiente)_

---

## Qué hace

| | |
|---|---|
| 🎙️ **Conversa por voz** | Hablas por el micrófono del navegador y te responde con voz en español |
| 🏃 **Planes reales** | 5K, 10K, 21K y maratón, con ritmos calculados, semanas de descarga y tapering |
| 🧠 **Recuerda** | Memoria en tres capas: si le cuentas que te molesta la rodilla, lo tiene en cuenta semanas después |
| 📧 **Te escribe** | Correo con la sesión del día, check-in nocturno y resumen semanal |
| 📷 **Lee tu reloj** | Le mandas una foto de la pantalla del reloj y registra el entrenamiento solo |
| 🔒 **Multiusuario** | Autenticación sin contraseñas y aislamiento estricto entre usuarios |

---

## La idea central

> **El LLM es la interfaz conversacional, no la fuente de verdad.**

Las reglas de entrenamiento (progresión del 10 %, polarización 80/20, semanas de descarga, tapering, ritmos por Riegel) viven en el dominio como **código determinista y testeado**. El modelo interpreta lo que quieres y te lo explica, pero no calcula nada.

Consecuencia visible: **Koda se niega a generar planes inviables.** Si pides un maratón en seis semanas sin haber corrido nunca, te dice que no y te propone un 21K.

---

## Arquitectura

```
Navegador (mobile-first)
        │  audio · texto · foto
        ▼
FastAPI  ──► Amazon Transcribe   (voz → texto)
        ──► Amazon Bedrock       (razonamiento + tool use)
        ──► Amazon Polly         (texto → voz, es-MX)
        ──► Amazon SES           (recordatorios por correo)
        ──► PostgreSQL           (perfil · planes · memoria)
```

**Hexagonal (puertos y adaptadores).** El dominio no importa `boto3` — hay un test que lo verifica. Cambiar de proveedor cuesta cuatro líneas en `container.py`.

📖 Documentación completa en [`docs/contexto/`](docs/contexto/00-CONTEXTO.md) · 📐 Decisiones en [`docs/adr/`](docs/adr/)

---

## Levantarlo en 5 minutos

**Requisitos:** Python 3.12+, PostgreSQL (o Docker), una cuenta de AWS con acceso a Bedrock, Transcribe, Polly y SES.

```powershell
git clone <url-del-repo>
cd koda-running-coach

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# rellena .env con tus credenciales

# comprueba que AWS responde antes de nada
python scripts/smoke_aws.py

alembic upgrade head
uvicorn app.main:app --reload
```

Abre `http://localhost:8000`. Introduce tu correo y sigue el enlace que recibas.

> ⚠️ **En móvil hace falta HTTPS**: `getUserMedia` no funciona sobre HTTP y no hay excepción de `localhost` desde otro dispositivo.

**Tests:**

```powershell
pytest                      # suite completa: sin red, sin coste
pytest tests/security -v    # aislamiento entre usuarios
```

---

## Estructura

```
app/
├── domain/            reglas de entrenamiento y puertos — cero dependencias externas
├── application/       casos de uso
├── infrastructure/    adaptadores de AWS, BD y almacenamiento
├── interfaces/        API HTTP y web
└── prompts/           prompts versionados
tests/{unit,integration,security,fakes}/
docs/{contexto,adr}/
```

---

## Decisiones de arquitectura

| ADR | Decisión |
|---|---|
| [001](docs/adr/ADR-001-pipeline-cascada.md) | Pipeline en cascada en lugar de speech-to-speech en tiempo real |
| [002](docs/adr/ADR-002-python-fastapi.md) | Python + FastAPI, frontend sin framework |
| [003](docs/adr/ADR-003-arquitectura-hexagonal.md) | Arquitectura hexagonal para aislar proveedores de IA |
| [004](docs/adr/ADR-004-aws-servicios-gestionados.md) | Servicios gestionados de AWS |
| [005](docs/adr/ADR-005-memoria-tres-capas.md) | Memoria en tres capas |
| [006](docs/adr/ADR-006-dominio-determinista.md) | Reglas de entrenamiento deterministas |
| [007](docs/adr/ADR-007-auth-enlace-magico.md) | Autenticación por enlace mágico |
| [008](docs/adr/ADR-008-entradas-multimodales.md) | Entradas multimodales |

Cada ADR incluye sus **consecuencias negativas**. Un ADR sin ellas es publicidad, no ingeniería.

---

## Seguridad

El aislamiento entre usuarios se aplica en cinco capas y se verifica con tests:

1. **Repositorios** — ningún método consulta datos personales sin `runner_id` en la firma
2. **HTTP** — la identidad sale del JWT, nunca del cuerpo de la petición
3. **Contexto del LLM** — una única función auditada lo ensambla
4. **Archivos** — URLs firmadas con caducidad y comprobación de propiedad
5. **Scheduler** — cada job va acotado a su runner

```powershell
pytest tests/security -v
```

Detalles en [`docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md`](docs/contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md).

---

## Roadmap

Fuera del alcance de esta entrega, con la solución identificada:

- **Recuperación semántica de memoria** con embeddings y `pgvector`, cuando los hechos por usuario crezcan
- **Streaming de respuesta** token a token + síntesis por frases, para bajar la latencia percibida a ~1,5 s
- **Análisis de técnica de carrera** por vídeo, mediante extracción de fotogramas
- **Speech-to-speech en tiempo real** con Amazon Nova 2 Sonic, para conversación con interrupciones
- **Integración con Strava y Garmin**, sustituyendo el registro por foto
- **EventBridge Scheduler + Lambda** en lugar de APScheduler, si escalara a miles de usuarios

---

## Aviso

Koda ofrece orientación de entrenamiento, **no consejo médico**. Ante dolor persistente o una lesión, consulta a un profesional de la salud.

---

*Prueba técnica · agosto de 2026*

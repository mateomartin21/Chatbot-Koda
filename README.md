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
| 📷 **Lee tu reloj** | Le mandas una foto de la pantalla del reloj, lee los números y da la sesión por hecha |
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

Abre `http://localhost:8000` — esa es la página pública. La aplicación está en
`http://localhost:8000/app/`: introduce tu correo y sigue el enlace que recibas.

> ⚠️ **En móvil hace falta HTTPS**: `getUserMedia` no funciona sobre HTTP y no hay excepción de `localhost` desde otro dispositivo. Por eso el despliegue no es el último paso de la lista, es lo que desbloquea la mitad del proyecto — ver abajo.

**Tests:**

```powershell
pytest                      # suite completa: sin red, sin coste
pytest tests/security -v    # aislamiento entre usuarios
```

---

## Ponerlo en internet

Tres contenedores en una instancia EC2 — PostgreSQL, la aplicación y Caddy, que pide
el certificado a Let's Encrypt al arrancar y lo renueva solo. No hace falta comprar
dominio.

```bash
git clone <url-del-repo> koda && cd koda
nano .env                       # DOMINIO, APP_BASE_URL y las credenciales
docker compose up -d --build
```

El runbook completo, con el grupo de seguridad, la IP elástica y qué mirar cuando algo
falla, está en **[docs/DESPLIEGUE.md](docs/DESPLIEGUE.md)**. El porqué de cada decisión
—y por qué App Runner y Lambda quedaron descartados— en
[ADR-019](docs/adr/ADR-019-una-instancia-y-caddy-para-el-https.md).

Para probar los contenedores en local, sin certificado:

```bash
POSTGRES_PASSWORD=local DOMINIO=localhost docker compose up -d db migraciones app
```

---

## Estructura

```
app/
├── domain/            reglas de entrenamiento y puertos — cero dependencias externas
├── application/       casos de uso
├── infrastructure/    adaptadores de AWS, BD y almacenamiento
├── interfaces/        API HTTP y web
│   └── web/           portada pública en /, aplicación en /app/
└── prompts/           prompts versionados
tests/{unit,integration,security,fakes}/
docs/{contexto,adr}/
```

---

## Decisiones de arquitectura

| ADR | Decisión |
|---|---|
| [001](docs/adr/ADR-001-pipeline-cascada.md) | Pipeline en cascada en lugar de speech-to-speech — *superseded por [011](docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md)* |
| [002](docs/adr/ADR-002-python-fastapi.md) | Python + FastAPI, frontend sin framework |
| [003](docs/adr/ADR-003-arquitectura-hexagonal.md) | Arquitectura hexagonal para aislar proveedores de IA |
| [004](docs/adr/ADR-004-aws-servicios-gestionados.md) | Servicios gestionados de AWS |
| [005](docs/adr/ADR-005-memoria-tres-capas.md) | Memoria en tres capas |
| [006](docs/adr/ADR-006-dominio-determinista.md) | Reglas de entrenamiento deterministas |
| [007](docs/adr/ADR-007-auth-enlace-magico.md) | Autenticación por enlace mágico |
| [008](docs/adr/ADR-008-entradas-multimodales.md) | Entradas multimodales |
| [009](docs/adr/ADR-009-groq-stt-temporal.md) | Groq Whisper como STT temporal |
| [010](docs/adr/ADR-010-sin-dominio-propio-para-ses.md) | Sin dominio propio para SES — se acepta el riesgo de spam |
| [011](docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md) | Voz en tiempo real con Nova Sonic y gateway de modelos con fallback |
| [012](docs/adr/ADR-012-tensiones-entre-reglas-de-entrenamiento.md) | Cómo se resuelven las contradicciones entre las reglas R1–R8 |
| [013](docs/adr/ADR-013-prompt-propio-para-el-modelo-de-voz.md) | Un prompt propio para el modelo de voz, y herramientas donde el fallo no cabe |
| [014](docs/adr/ADR-014-jobs-en-memoria.md) | Los avisos programados viven en memoria y se reconstruyen al arrancar |
| [015](docs/adr/ADR-015-direccion-visual-y-presupuesto-de-movimiento.md) | Una dirección visual propia y un presupuesto de movimiento — *superseded por [016](docs/adr/ADR-016-el-acento-se-aleja-del-naranja-de-strava.md)* |
| [016](docs/adr/ADR-016-el-acento-se-aleja-del-naranja-de-strava.md) | El acento se aleja del naranja de Strava, y seis animaciones más |
| [017](docs/adr/ADR-017-la-foto-se-reprocesa-antes-de-salir.md) | La foto se reprocesa antes de salir del servidor |
| [018](docs/adr/ADR-018-koda-tiene-cara-y-la-app-se-instala.md) | Koda tiene cara, y la aplicación se instala en el móvil |
| [019](docs/adr/ADR-019-una-instancia-y-caddy-para-el-https.md) | Una instancia EC2 con Caddy, y el HTTPS sin comprar dominio |
| [020](docs/adr/ADR-020-nova-habla-y-sonnet-decide.md) | Nova Sonic habla, el modelo grande decide |
| [021](docs/adr/ADR-021-una-sola-conversacion-por-runner.md) | Una sola conversación por runner, que sobrevive a cerrar la pestaña |
| [022](docs/adr/ADR-022-el-correo-tiene-que-llegar-a-cualquiera.md) | El correo tiene que llegarle a alguien que no conozco |

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

- **Editar el plan sin regenerarlo.** Hoy pedir otro plan reemplaza al anterior: no se
  puede mover una sesión ni decir "esta semana viajo". Es una decisión, no un olvido —
  un plan es el resultado de un cálculo completo, y dejarlo editar suelto abre la puerta
  a planes que ya no cumplen R1–R8. La forma correcta es una herramienta `ajustar_plan`
  que **vuelva a pasar por el dominio**, no un editor de sesiones.
- **Barge-in**: interrumpir a Koda mientras habla. Nova Sonic lo soporta; el cliente no.
- **Recuperación semántica de memoria** con embeddings y `pgvector`, cuando los hechos por usuario crezcan
- **Higiene de memoria por caducidad**: hoy los hechos se deduplican y se pueden marcar no
  vigentes, pero nada caduca solo. Una lesión de hace ocho meses no debería condicionar el
  plan de hoy ([05-MEMORIA §4.3](docs/contexto/05-MEMORIA.md))
- **Análisis de técnica de carrera** por vídeo, mediante extracción de fotogramas
- **Integración con Strava y Garmin**, sustituyendo el registro por foto
- **EventBridge Scheduler + Lambda** en lugar de APScheduler, si escalara a miles de usuarios

---

## Aviso

Koda ofrece orientación de entrenamiento, **no consejo médico**. Ante dolor persistente o una lesión, consulta a un profesional de la salud.

---

*Prueba técnica · agosto de 2026*

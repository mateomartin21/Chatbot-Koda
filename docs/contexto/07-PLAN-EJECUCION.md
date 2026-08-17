# 07 · Plan de ejecución

**Del jueves 13 al lunes 17 de agosto de 2026.**

> Cada bloque termina con **algo que funciona de punta a punta** y un commit. Nada de "el viernes termino la capa de datos". Si el domingo se cae el mundo, quieres tener algo demostrable desde el día 1.

---

## ⚠️ Aviso de alcance, sin adornos

En la v3 se añadieron **autenticación multiusuario** y **entradas multimodales** a un proyecto de 4 días que ya era ambicioso, y **la cuenta de AWS todavía no existe**. Ambas adiciones son correctas — la de usuarios es directamente necesaria — pero hay que ser honesto con la aritmética.

**Prioridad, en este orden. Si algo se cae, se cae de abajo hacia arriba:**

```
1. Pipeline de voz funcionando                    ← sin esto no hay proyecto
2. Autenticación y aislamiento por usuario        ← sin esto hay fuga de datos
3. Dominio de entrenamiento determinista          ← es la tesis del proyecto
4. Memoria de 3 capas                             ← punto extra del enunciado
5. Recordatorios por correo                       ← punto extra del enunciado
6. Entrada de texto                               ← 1 hora, alto valor
7. Entrada de fotos                               ← la feature que se recuerda
8. Documentación, ADRs y vídeo de demo            ← se hace el lunes, no se negocia
─────────────────────────────────────────────────────────────
9. Entrada de vídeo                               ← ❌ lo primero que se corta
10. Streaming de respuesta token a token          ← ❌ lo segundo que se corta
```

Lo que quede fuera **se documenta como Roadmap en el README**. Eso se lee como criterio, no como falta de tiempo.

---

## 🔹 Día 0 — Jueves 13, esta noche (~4 h) · *Desbloquear AWS*

Hoy no se programa lógica de negocio. Hoy se elimina el riesgo que puede hundir el proyecto.

- [ ] **Crear la cuenta de AWS.** Tarjeta obligatoria aunque no cobren. Región **`us-east-1`**
- [ ] **Alarma de facturación a 5 USD** (Billing → Budgets). Dos minutos y duermes tranquilo
- [ ] **Usuario IAM** con permisos mínimos: Transcribe, Bedrock, Polly, SES. **Nunca credenciales root**
- [ ] **Bedrock → Model access**: habilitar los modelos que vas a usar
- [ ] **SES → verificar tu correo** (y el del evaluador, por el sandbox)
- [ ] Repo, entorno virtual, estructura de carpetas de [01](01-ARQUITECTURA.md), `.gitignore`, `.env.example`
- [ ] Copiar `docs/` completo al repo y hacer el primer commit
- [ ] Escribir `scripts/smoke_aws.py`: transcribe un audio, llama a Bedrock, genera un MP3 con Polly y se manda un correo con SES

**Definición de terminado:** `python scripts/smoke_aws.py` toca los cuatro servicios sin error.

```
🚦 COMPUERTA DE DECISIÓN — antes de dormir

  ✅ smoke_aws.py pasa  →  seguimos con el plan A, cero cambios.

  ❌ no pasa            →  NO gastes el viernes peleando con AWS.
                          Cambias 4 adaptadores en container.py:
                            STT → Groq Whisper · LLM → Gemini
                            TTS → Gemini TTS   · Email → Resend
                          Dominio, auth, memoria, web y scheduler: intactos.
```

`git commit -m "chore: scaffolding + verificación de servicios AWS"`

---

## 🔹 Día 1 — Viernes 14 (~7 h) · *Identidad primero, luego la voz*

**Por qué la autenticación va primero y no al final:** cada endpoint y cada repositorio se escribe desde el minuto uno recibiendo `runner_id`. Si dejas la auth para el domingo, tendrás que reescribir todas las firmas — y ahí es exactamente donde se cuelan los bugs de aislamiento que este proyecto pretende evitar.

**Mañana (~3 h) — Autenticación**
- [ ] Modelos `runners` y `tokens_acceso` + primera migración de Alembic
- [ ] `POST /api/auth/solicitar` y `GET /api/auth/canjear` ([03 §3](03-MULTIUSUARIO-Y-SEGURIDAD.md))
- [ ] `get_current_runner()` en `deps.py`
- [ ] Pantalla de entrada: campo de correo → "revisa tu bandeja"
- [ ] **Los dos primeros tests de `tests/security/`**: ventana del token y token caducado

**Tarde (~4 h) — Pipeline de voz**
- [ ] Puertos `STTPort` / `TTSPort` / `LLMPort`
- [ ] Adaptadores `transcribe_aws.py`, `bedrock_converse.py`, `polly.py`
- [ ] Caso de uso `procesar_mensaje` (voz **y texto** desde el principio — es una línea)
- [ ] `POST /api/mensajes` con `Depends(get_current_runner)`
- [ ] `index.html` mínimo: botón de micrófono + campo de texto → burbujas → reproducir respuesta
- [ ] `coach_system.md` v1

**Definición de terminado:** entras con tu correo, hablas al navegador y te responde con voz. **El corazón del proyecto, ya con usuarios.**

`git commit -m "feat: autenticación por enlace mágico + pipeline de voz"`

---

## 🔹 Día 2 — Sábado 15 (~7 h) · *Cerebro de entrenador + memoria*

**Mañana (~4 h) — Dominio**
- [ ] Entidades, value objects, `paces.py` con Riegel
- [ ] Estrategias `Plan5K` / `Plan10K` / `Plan21K` / `Plan42K` + factory
- [ ] **Los 6 tests de dominio de [02 §5](02-DOMINIO-RUNNING.md), escritos primero.** Aquí sí vale TDD: son funciones puras, instantáneas y gratis
- [ ] Test de arquitectura ([01](01-ARQUITECTURA.md)) en CI

**Tarde (~3 h) — Memoria y herramientas**
- [ ] Repositorios SQLAlchemy, **todos con `runner_id` en la firma**
- [ ] `construir_contexto()` — las tres capas de [05](05-MEMORIA.md)
- [ ] Extracción de hechos en segundo plano
- [ ] Tool use con las herramientas de [06 §4](06-PROMPTS.md)
- [ ] **Test de aislamiento del contexto**: los hechos de B no aparecen en el prompt de A

**Definición de terminado:** por voz obtienes un plan real de 12 semanas; cierras sesión, vuelves, y Koda se acuerda.

`git commit -m "feat: dominio de entrenamiento + memoria de 3 capas"`

---

## 🔹 Día 3 — Domingo 16 (~7 h) · *Correos, fotos, móvil y despliegue*

**Mañana (~3 h) — Recordatorios**
- [ ] APScheduler con jobstore en PostgreSQL
- [ ] Los tres correos: sesión diaria, check-in nocturno, resumen semanal
- [ ] Plantillas HTML + versión en texto plano + enlace de baja
- [ ] Zona horaria del runner, no UTC del servidor

**Tarde (~2 h) — Fotos**
- [ ] Subida con `<input capture>`, saneado con Pillow, **EXIF eliminado** ([04 §3.3](04-ENTRADAS-MULTIMODALES.md))
- [ ] Herramienta `extraer_datos_de_captura` con umbral de confianza
- [ ] Probar con una foto real de un reloj

**Noche (~2 h) — Pulido y despliegue**
- [ ] **Las cuatro trampas del audio en móvil** y prueba **en un móvil real**
- [ ] Deploy con HTTPS + PostgreSQL gestionado
- [ ] GitHub Actions: `ruff` + `pytest` en cada push

**Definición de terminado:** está en internet, se usa desde cualquier móvil, manda correos solo y lee capturas de reloj.

`git commit -m "feat: recordatorios por correo + entrada por foto + deploy"`

> **⏰ Punto de control de las 20:00.** Si los correos o el aislamiento no están cerrados: **congela features**. El vídeo y el streaming ya no existen. El lunes es para documentar, no para programar.

---

## 🔹 Día 4 — Lunes 17 (~5 h) · *Presentación* — **cero features nuevas**

- [ ] `README.md` completo: qué es, capturas, arquitectura, cómo levantarlo en 5 min
- [ ] Los 8 ADRs de `docs/adr/` revisados y coherentes con lo que realmente construiste
- [ ] Repaso de errores y degradación ([01](01-ARQUITECTURA.md)): ¿y si Bedrock falla? ¿y si el audio es inaudible? ¿y si SES rebota?
- [ ] Prueba de humo completa **con un usuario nuevo desde cero**, en un navegador limpio
- [ ] Verificar que `tests/security/` pasa entero
- [ ] **Vídeo de demo de 2–3 minutos**, grabando la pantalla del móvil:
  1. Entrar con el correo (10 s)
  2. Pedir un plan de 10K por voz (30 s)
  3. Foto del reloj → se registra el entrenamiento solo (30 s)
  4. **Cerrar sesión, volver a entrar, y que se acuerde de la rodilla** (30 s) ← el momento clave
  5. Enseñar el correo recibido (15 s)
- [ ] Entrega

**Muchos evaluadores no van a levantar tu proyecto. El vídeo es lo que realmente ven.** Grábalo aunque vayas justo de tiempo: entre un vídeo y una feature más, el vídeo gana siempre.

---

## Definición de terminado (aplica a todo)

Una tarea no está hecha hasta que:

1. Funciona de punta a punta desde la interfaz, no solo en un test
2. Tiene al menos un test que la cubre
3. Falla con elegancia si el servicio externo se cae
4. Está commiteada con un mensaje que explica el porqué
5. Si tomó una decisión discutible, hay un ADR

---

## Lo que NO se hace, pase lo que pase

- Refactorizar algo que ya funciona "para que quede más bonito"
- Añadir una feature que no está en la lista de prioridades
- Cambiar de proveedor de IA el domingo porque otro "parece mejor"
- Empezar el lunes cualquier cosa que no sea documentación o el vídeo

**Congelar el alcance a tiempo es una habilidad de ingeniería, y en una prueba con fecha límite es precisamente lo que se está midiendo.**

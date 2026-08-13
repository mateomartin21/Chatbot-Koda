# ADR-009 · Groq Whisper como STT temporal mientras Transcribe se desbloquea

**Estado:** Aceptado
**Fecha:** 2026-08-14

## Contexto

La cuenta de AWS se creó el 2026-08-12. Amazon Bedrock, Polly y SES ya responden correctamente
(verificado con `scripts/smoke_aws.py`), pero Amazon Transcribe rechaza toda llamada con
`SubscriptionRequiredException: The AWS Access Key Id needs a subscription for the service`. Es
la restricción habitual de AWS a cuentas nuevas para servicios de ML/reconocimiento, pendiente de
verificación automática por parte de Amazon — no depende de la configuración del proyecto (la
misma cuenta, región y usuario IAM sí sirven de punta a punta para los otros tres servicios).

El Día 1 empieza con el pipeline de voz como prioridad #1 ("sin esto no hay proyecto"). Seguir
esperando a que AWS desbloquee el servicio, sin fecha garantizada, pone en riesgo el resto del día.

## Decisión

Activar temporalmente el `STTPort` con **Groq Whisper** (`PROVIDER_STT=fallback` en `.env`) en
lugar de Amazon Transcribe, mientras se resuelve el acceso en AWS. `LLM`, `TTS` y `Email` se
quedan en AWS — no es el Plan B completo del [ADR-004](ADR-004-aws-servicios-gestionados.md), es
un cambio acotado a un solo puerto.

El adaptador `transcribe_aws.py` se escribió igualmente (mismo patrón que el smoke test: sube el
audio a S3, lanza el job batch, lee el resultado), para que volver a AWS cuando se desbloquee sea
cambiar `PROVIDER_STT` de vuelta a `aws` — sin código nuevo. **No se ha podido probar contra el
servicio real** por el bloqueo de cuenta.

## Alternativas consideradas

**Esperar a que AWS desbloquee la cuenta.** Descartado por ahora: sin fecha garantizada, y el
pipeline de voz es la prioridad más alta del día. Se puede revertir en cualquier momento si se
desbloquea — ver más abajo.

**Abrir caso de soporte con AWS y esperar la respuesta antes de decidir.** Válido en paralelo, pero
no bloqueante: no tiene sentido parar el desarrollo del día por una respuesta de soporte sin SLA
garantizado en el plan Basic.

**Cambiar también LLM/TTS/Email al Plan B completo del ADR-004.** Descartado: esos tres servicios
ya funcionan, cambiarlos sin motivo sería trabajo y riesgo innecesarios.

## Consecuencias

### Positivas

- El pipeline de voz no queda bloqueado por un trámite de AWS fuera de nuestro control.
- La arquitectura hexagonal cumple exactamente lo que prometía: el cambio fue un archivo nuevo
  (`groq_whisper.py`) y una línea en `container.py`.
- Groq no pide tarjeta de crédito, reduce fricción de arranque frente a AWS.

### Negativas

- **Dos proveedores de IA en producción en vez de uno** (AWS + Groq), con dos claves distintas
  que rotar y dos paneles que vigilar durante el resto del proyecto.
- **`transcribe_aws.py` esta sin probar contra el servicio real.** Si Transcribe se desbloquea,
  hay que validarlo antes de confiar en el cambio de vuelta — no asumir que compila y ya funciona.
- Latencia y calidad de transcripción de Groq Whisper no se han comparado formalmente contra
  Transcribe para es-MX; se acepta sin ese benchmark por el plazo del proyecto.
- Si Groq tiene una caída o cambia límites de uso gratuito, el pipeline de voz vuelve a quedar
  expuesto a un único proveedor no-AWS sin plan de contingencia adicional.

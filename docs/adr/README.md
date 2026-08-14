# Architecture Decision Records

Registro de las decisiones de arquitectura de Koda. Un ADR documenta **una** decisión: por qué se tomó, qué se descartó y qué consecuencias tiene — incluidas las malas.

**Un ADR no se edita.** Si una decisión cambia, se escribe uno nuevo que *supersede* al anterior y se marca el viejo como `Superseded by ADR-XXX`. El historial de cómo evolucionó el criterio es parte del valor.

## Formato

```markdown
# ADR-XXX · Título

**Estado:** Aceptado | Superseded by ADR-YYY
**Fecha:** AAAA-MM-DD

## Contexto
Qué situación obliga a decidir.

## Decisión
Qué se decide, en una frase clara.

## Alternativas consideradas
Qué más se evaluó y por qué se descartó.

## Consecuencias
### Positivas
### Negativas
Las negativas son obligatorias. Un ADR sin consecuencias negativas es publicidad, no ingeniería.
```

## Índice

| ADR | Decisión | Estado |
|---|---|---|
| [001](ADR-001-pipeline-cascada.md) | Pipeline en cascada en lugar de speech-to-speech en tiempo real | Superseded by [011](ADR-011-nova-sonic-y-gateway-de-modelos.md) |
| [002](ADR-002-python-fastapi.md) | Python + FastAPI, frontend sin framework, n8n descartado | Aceptado |
| [003](ADR-003-arquitectura-hexagonal.md) | Arquitectura hexagonal para aislar proveedores de IA | Aceptado |
| [004](ADR-004-aws-servicios-gestionados.md) | Servicios gestionados de AWS para IA y correo | Aceptado |
| [005](ADR-005-memoria-tres-capas.md) | Memoria en tres capas en lugar de historial completo | Aceptado |
| [006](ADR-006-dominio-determinista.md) | Reglas de entrenamiento deterministas, no delegadas al LLM | Aceptado |
| [007](ADR-007-auth-enlace-magico.md) | Autenticación por enlace mágico, sin contraseñas | Aceptado |
| [008](ADR-008-entradas-multimodales.md) | Entradas multimodales con vídeo como alcance opcional | Aceptado |
| [009](ADR-009-groq-stt-temporal.md) | Groq Whisper como STT temporal mientras Transcribe se desbloquea | Aceptado |
| [010](ADR-010-sin-dominio-propio-para-ses.md) | Sin dominio propio para SES — se acepta el riesgo de spam | Aceptado |
| [011](ADR-011-nova-sonic-y-gateway-de-modelos.md) | Voz en tiempo real con Nova Sonic y gateway de modelos con fallback | Aceptado |
| [012](ADR-012-tensiones-entre-reglas-de-entrenamiento.md) | Cómo se resuelven las contradicciones entre las reglas R1–R8 | Aceptado |
| [013](ADR-013-prompt-propio-para-el-modelo-de-voz.md) | Un prompt propio para el modelo de voz, y herramientas donde el fallo no cabe | Aceptado |

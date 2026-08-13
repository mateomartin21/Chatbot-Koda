# ADR-004 · Servicios gestionados de AWS para IA y correo

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

El proyecto necesita cuatro capacidades externas: transcripción de voz, razonamiento multimodal, síntesis de voz en español y envío de correo. La planificación v1 las resolvía con proveedores mixtos (Groq + Google Gemini). En la v2 se decidió construir sobre **AWS**.

Un dato relevante: **no existía cuenta de AWS al empezar**, y el alcance elegido fue *AWS solo para IA y correo*, no infraestructura serverless completa.

## Decisión

| Capacidad | Servicio |
|---|---|
| Voz → texto | **Amazon Transcribe** (`es-MX`) |
| Razonamiento | **Amazon Bedrock**, Converse API con *tool use* |
| Texto → voz | **Amazon Polly**, voz generativa `es-MX` |
| Correo | **Amazon SES** v2 |

La aplicación **no** se despliega en Lambda ni usa DynamoDB: corre como un contenedor normal contra PostgreSQL.

## Alternativas consideradas

**Seguir con Groq + Gemini (plan v1).** Alta instantánea, sin tarjeta, sin espera. Se mantiene como **plan B documentado** precisamente porque sigue siendo una opción válida. Se pospuso porque unificar en un proveedor simplifica credenciales, facturación y observabilidad, y porque AWS es una competencia demandada.

**Serverless completo (Lambda + API Gateway + DynamoDB + EventBridge).** Descartado explícitamente. Se ve bien en un CV, pero el depurado local es doloroso y la configuración de IAM y despliegue se come alrededor de día y medio de los cuatro disponibles. **Con plazo corto, se optimiza el producto terminado, no el escaparate de servicios.**

**Amazon Lex** para la conversación. Descartado: está pensado para flujos de intenciones y *slots*, no para conversación abierta con un LLM. Sería remar contra el diseño de la herramienta.

**TTS de Groq (Orpheus).** Descartado por un motivo concreto: **solo soporta inglés y árabe**. Koda habla español mexicano.

## Consecuencias

### Positivas

- Un solo proveedor: unas credenciales, una factura, un sitio donde mirar métricas.
- **Polly devuelve MP3 directamente**, reproducible en el navegador sin conversión. Esto eliminó por completo la dependencia de `ffmpeg` que tenía el plan v1 con Telegram — un ahorro real de horas.
- La Converse API de Bedrock **unifica modelos**: cambiar de modelo es cambiar un string, y da acceso a modelos Claude sin contratar la API de Anthropic aparte.
- Transcribe soporta `es-MX` nativamente, con puntuación automática.

### Negativas

- **Riesgo de arranque alto y real:** crear la cuenta, verificar la tarjeta, habilitar el acceso a los modelos de Bedrock por región y sacar SES del sandbox son cuatro trámites que pueden fallar. Es el riesgo número uno del proyecto y por eso existe una compuerta de decisión en [07-PLAN-EJECUCION](../contexto/07-PLAN-EJECUCION.md).
- **SES arranca en sandbox:** solo envía a direcciones verificadas hasta que se aprueba el acceso de producción (~24 h de revisión). Para la demo basta con verificar los correos implicados, pero es una limitación que hay que conocer de antemano.
- **Acoplamiento comercial** a un proveedor. Mitigado por [ADR-003](ADR-003-arquitectura-hexagonal.md): el cambio cuesta una tarde, no una reescritura.
- Nova 2 Sonic, la opción más interesante de AWS para voz, **no se aprovecha** por lo decidido en [ADR-001](ADR-001-pipeline-cascada.md).

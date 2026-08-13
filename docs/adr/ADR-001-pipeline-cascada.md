# ADR-001 · Pipeline en cascada en lugar de speech-to-speech en tiempo real

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

Koda es un chatbot de voz. Existen dos formas de construirlo:

- **Cascada:** `audio → STT → LLM → TTS → audio`. Tres servicios encadenados.
- **Speech-to-speech:** un único modelo recibe audio y devuelve audio, con detección de turnos e interrupciones. En AWS, **Amazon Nova 2 Sonic** (`amazon.nova-2-sonic-v1:0`).

Nova 2 Sonic ofrece latencia de ~500 ms frente a los 3–5 s de la cascada, y conversación mucho más natural.

## Decisión

Se implementa el **pipeline en cascada** como arquitectura del producto. Nova 2 Sonic queda como exploración opcional si el tiempo lo permite.

## Alternativas consideradas

**Nova 2 Sonic como núcleo.** Descartado por cuatro motivos:

1. Se invoca con `InvokeModelWithBidirectionalStream`, no con una petición HTTP normal. Exige WebSocket entre navegador y backend **y** entre backend y Bedrock. Es un proyecto en sí mismo dentro de un plazo de 4 días.
2. Solo está disponible en 4 regiones.
3. Al ser una caja negra de audio a audio, **no hay un punto natural donde insertar la lógica de dominio** — que es la tesis del proyecto ([ADR-006](ADR-006-dominio-determinista.md)).
4. No produce texto como subproducto, y el texto se necesita para la memoria, las burbujas de la interfaz, los logs y las herramientas.

**Modelo híbrido** (cascada para acciones, realtime para charla). Descartado: dos rutas de código que mantener y depurar, con el mismo plazo.

## Consecuencias

### Positivas

- **Depurable eslabón por eslabón.** Cuando una respuesta es mala, se ve exactamente dónde falló: transcripción, razonamiento o síntesis.
- **El texto sale gratis** y se necesitaba de todas formas.
- **Cada pieza es intercambiable** — es lo que hace viable el plan B de proveedor.
- **Coste predecible y medible** por eslabón.

### Negativas

- **Latencia de 3–5 s** frente a los ~500 ms del speech-to-speech. Se mitiga con feedback visual por etapas, no con arquitectura: el usuario ve su transcripción aparecer mientras el modelo piensa.
- **No hay interrupciones.** El usuario no puede cortar al coach a media frase, algo que en una conversación real es natural.
- **Se pierde la prosodia del usuario.** El tono de voz (cansancio, frustración) se destruye al convertir a texto. Un modelo speech-to-speech podría detectar que alguien suena agotado; Koda no.

Esa última es la pérdida más interesante y conviene reconocerla: en una app de coaching, *cómo* se dice algo tiene información real.

# ADR-011 · Voz en tiempo real con Nova Sonic y gateway de modelos con fallback

**Estado:** Aceptado
**Fecha:** 2026-08-13
**Supersede a:** [ADR-001](ADR-001-pipeline-cascada.md)

## Contexto

[ADR-001](ADR-001-pipeline-cascada.md) eligió el pipeline en cascada (`audio → STT → LLM →
TTS → audio`) y descartó el speech-to-speech, aceptando 3–5 s de latencia como
consecuencia negativa. Con la cascada ya funcionando de punta a punta, esa latencia
resultó ser el defecto más visible del producto: se siente como formulario, no como
conversación — justo lo contrario de lo que Koda pretende ser.

Se revisaron los cuatro motivos por los que ADR-001 descartó Nova Sonic, contra la
documentación y el SDK actuales:

| Objeción de ADR-001 | Estado verificado (2026-08-13) |
|---|---|
| "Exige WebSocket, es un proyecto en sí mismo" | **Cierto, y se subestimó.** Además necesita un SDK aparte (ver abajo) y reescribir la captura de audio del navegador con Web Audio API. |
| "Solo está en 4 regiones" | **Resuelto.** `us-east-1`, la región que ya usa el proyecto, lo soporta. |
| "No hay punto donde insertar la lógica de dominio" | **Resuelto.** Nova Sonic soporta *tool use*, el mismo enganche que se planeaba para Bedrock Converse. |
| "No produce texto, y hace falta para memoria, burbujas y logs" | **Resuelto.** Emite transcripción ASR del usuario y texto de la respuesta como eventos del stream. |

En paralelo surgió una segunda necesidad: que un modelo caído no deje al usuario sin
respuesta. Lo que había era un reintento de *la misma* llamada, que no protege de nada
si el problema es el modelo o el proveedor.

## Decisión

**Dos niveles, con degradación automática entre ellos:**

```
Turno de conversación
├─ Nivel 0: Nova Sonic — audio a audio en tiempo real (~1 s)
└─ Nivel 1 (fallback): cascada STT → [Model Gateway] → TTS
                                          ├─ Bedrock Sonnet   (calidad)
                                          ├─ Bedrock barato   (mismo proveedor)
                                          ├─ Groq             (proveedor distinto)
                                          └─ mensaje amable de degradación
```

1. **Nova Sonic como camino principal de voz y texto**, por un WebSocket `/ws/voz`
   detrás del puerto `VozRealtimePort`. El texto también pasa por ahí para que la voz
   y la latencia sean las mismas escribas o hables.
2. **La cascada se conserva íntegra como fallback.** Si Nova Sonic no abre sesión o
   termina sin responder, el frontend reintenta por `POST /api/mensajes` sin que el
   usuario haga nada distinto.
3. **`ModelGatewayLLM`**: cadena ordenada de `LLMPort` con timeout por intento. Prueba
   proveedores *distintos* hasta que uno responde; si todos fallan, propaga el error y
   la capa de aplicación decide el mensaje de degradación.
4. **Prompt caching** en Bedrock (`cachePoint` tras el system prompt), que es idéntico
   en cada petición: ~10 % del coste de entrada en un acierto de caché.

Esto adopta a propósito el **modelo híbrido que ADR-001 descartó** ("dos rutas de código
que mantener"). La diferencia con entonces: la cascada ya está construida, probada y
pagada — mantenerla como red de seguridad no cuesta trabajo extra, y es lo que permitió
arriesgarse con Nova Sonic sin poner en riesgo la entrega.

## Alternativas consideradas

**Quedarse en la cascada y mitigar solo la percepción** (feedback visual por etapas, ya
implementado). Es lo que mandaba ADR-001 y sigue siendo defendible: cero riesgo. Se
descartó porque la diferencia con tiempo real no es cosmética — es la diferencia entre
"esperar a que un sistema conteste" y "conversar".

**Un pipeline multi-proveedor completo al estilo de *AI Engineering* (Chip Huyen)**, con
presupuesto de tokens, enrutado por coste y caché semántica. Descartado: son patrones
para producción con tráfico real. De ese libro se tomó lo que aplica a esta escala — el
*model gateway* con fallback ordenado y el prompt caching — y se dejó fuera lo demás.

**Sustituir la cascada por Nova Sonic** en vez de mantener las dos. Descartado tras las
pruebas: Nova Sonic falla de formas que hoy no controlamos del todo, y quedarse sin
camino alternativo sería inaceptable el día de la demo.

## Consecuencias

### Positivas

- **Latencia de ~1 s frente a 3–5 s**, verificado en navegador. Es el cambio que más se
  nota usando el producto.
- **Voz notablemente mejor** que Polly, y ahora la misma escribas o hables.
- **Resiliencia real**, no teórica: caen los tres tiers del gateway y todavía hay
  mensaje de degradación; se cae Nova Sonic entero y la conversación sigue por la
  cascada. Cubierto por tests con dobles.
- La arquitectura hexagonal **volvió a pagarse sola**: Nova Sonic entró como un puerto
  nuevo sin tocar dominio ni casos de uso, y el gateway sustituyó al `LLMPort` anterior
  cambiando una línea de `container.py`.
- El prompt caching abarata cada turno de la cascada sin cambiar comportamiento.

### Negativas

- **Dos rutas de voz que mantener y depurar** — exactamente lo que ADR-001 quiso evitar.
- **Dependencia de un SDK pre-1.0 aparte de boto3.** Nova Sonic usa
  `InvokeModelWithBidirectionalStream`, que boto3 no soporta: hace falta
  `aws_sdk_bedrock_runtime` + `smithy_aws_core`. Resuelve credenciales **solo por
  variables de entorno**, así que hubo que exportarlas explícitamente
  (`exportar_credenciales_a_entorno`) — la misma clase de bug silencioso que ya obligó a
  crear `cliente_aws()`.
- **El comportamiento real del modelo no coincide con su documentación**, y cada
  diferencia costó una ronda de depuración con el producto en la mano:
  - `completionEnd` (el fin de turno documentado) **no siempre llega**; hay que cerrar
    por el `contentEnd` de AUDIO con `stopReason=END_TURN` más un margen.
  - El texto llega en dos etapas, `SPECULATIVE` y `FINAL`, y **la confirmada tampoco
    llega siempre** (sobre todo en turnos de voz). La interfaz muestra el adelanto y lo
    sustituye solo si llega algo más completo.
  - En modo texto **exige un flujo de audio en silencio** para responder; sin él la
    sesión queda inerte y solo devuelve `usageEvent`. Está en el sample oficial, no en
    la documentación.
  - Genera audio **mucho más rápido que en tiempo real**, así que el navegador tiene
    segundos de audio agendado cuando el turno ya "terminó": cerrar el `AudioContext` al
    acabar el turno cortaba la respuesta a media frase.
- **Sin barge-in**: no se puede interrumpir a Koda hablando, aunque el modelo lo soporta.
- **La voz sigue sin ser `es-MX`.** Nova Sonic solo ofrece `es-US` (`lupe`, `carlos`);
  Polly sí tenía `es-MX`. Se perdió algo de cercanía regional a cambio de la latencia.
- **Un proveedor más del que depender** (Groq como LLM, no solo como STT).
- El fallback entre tiers **añade latencia en el peor caso**: hay que esperar el timeout
  de cada tier antes de pasar al siguiente. Por eso el timeout por intento es corto (4 s).
- **El audio en tiempo real no tiene test automatizado realista.** Los tests cubren
  autenticación, reenvío de eventos y disparo del fallback con dobles; que se escuche
  bien solo se comprueba a mano en un navegador.

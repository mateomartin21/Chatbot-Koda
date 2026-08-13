# ADR-005 · Memoria en tres capas en lugar de historial completo

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

El enunciado valora como punto extra que el chatbot **recuerde conversaciones anteriores**. La implementación ingenua es guardar todos los mensajes y reenviarlos en cada llamada al modelo.

Eso tiene tres problemas que se agravan con el uso: el coste crece cuadráticamente, el ruido dificulta que el modelo encuentre el dato relevante, y llega un punto en que no cabe en la ventana de contexto — y truncar borra justo lo antiguo, que suele ser lo valioso.

## Decisión

Memoria en **tres capas**, cada una con su almacenamiento y su propósito:

1. **Perfil estructurado** — columnas de base de datos (edad, nivel, días disponibles, objetivo, plan activo). Siempre presente, exacto, barato.
2. **Ventana corta** — los últimos ~10 turnos, tal cual, para la continuidad conversacional.
3. **Hechos duraderos** — un modelo pequeño extrae hechos categorizados (`lesion`, `preferencia`, `contexto`, `logro`, `restriccion`) tras cada conversación, en segundo plano.

## Alternativas consideradas

**Historial completo en el prompt.** Descartado por coste creciente y por el límite duro de contexto.

**Resumen rodante** (resumir la conversación y arrastrar el resumen). Mejor que el historial, pero pierde información de forma impredecible: el resumen decide qué olvidar sin criterio, y los datos concretos (una fecha de carrera, una molestia) se disuelven en generalidades.

**RAG con embeddings y `pgvector` desde el día uno.** Es la solución correcta a gran escala. Descartada **para esta semana** porque con un usuario de demo y unas decenas de hechos, traerlos todos es más simple, más barato y más predecible. Queda documentada en el README como evolución natural. *Saber dónde se rompe tu solución vale más que implementar lo complejo sin necesidad.*

## Consecuencias

### Positivas

- **El coste por mensaje es prácticamente constante** (~2 100 tokens) aunque el runner lleve un año usando la app. Este es el argumento central del diseño.
- Cada tipo de información vive donde le corresponde: lo que es un dato es una columna, no una memoria difusa que el modelo pueda malinterpretar.
- La capa 3 produce el efecto que impresiona en una demo: el coach se acuerda de una lesión mencionada semanas atrás y adapta el plan.
- El punto único de ensamblado (`construir_contexto`) es también la **frontera de aislamiento entre usuarios** ([ADR-007](ADR-007-auth-enlace-magico.md) y [03](../contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md)).

### Negativas

- **Más piezas móviles** que un historial plano: extracción, deduplicación, contradicciones y caducidad por categoría. Cada una puede fallar.
- **La extracción puede equivocarse.** Un hecho mal extraído se inyecta en todas las conversaciones futuras, y ese error es persistente y silencioso. Se mitiga con un umbral de confianza y marcando hechos como no vigentes en lugar de borrarlos.
- **Se pierde el detalle de conversaciones antiguas.** Koda recordará *que* le molesta la rodilla, pero no las palabras exactas con que lo contó.
- Sin recuperación semántica, con muchos hechos por usuario habría que elegir cuáles inyectar. Hoy se resuelve con un límite de 25 y caducidad por categoría — una solución suficiente, no elegante.

# ADR-006 · Reglas de entrenamiento deterministas, no delegadas al LLM

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

Koda genera planes de entrenamiento para 5K, 10K, 21K y maratón. Un LLM moderno sabe bastante de entrenamiento de running: se le puede pedir *"genera un plan de 10K para un principiante"* y devolverá algo razonable en tres segundos, sin escribir una línea de lógica.

La alternativa es codificar las reglas de entrenamiento en el dominio y usar el LLM solo como interfaz conversacional.

## Decisión

**Las reglas de entrenamiento viven en `app/domain/training/`, en código determinista y testeado.** El LLM interpreta la intención del usuario, llama a la herramienta correspondiente y explica el resultado, pero **no calcula nada**.

Se implementan como regla de dominio: progresión del 10 %, polarización 80/20, semanas de descarga, tapering, ritmos derivados por Riegel, mínimos de semanas por distancia, día de descanso obligatorio y techo de la tirada larga.

## Alternativas consideradas

**Delegar la generación del plan al LLM.** Mucho más rápido de construir. Descartado por cuatro razones:

1. **No es reproducible.** El mismo runner con la misma petición obtiene planes distintos. Para un producto de entrenamiento, donde el usuario compara la semana 3 con la semana 4, eso es inaceptable.
2. **No es testeable.** No se puede escribir un test que garantice que el volumen nunca sube más del 10 %.
3. **No es auditable.** Si un plan resulta lesivo, no hay forma de explicar de dónde salió.
4. **No se puede demostrar en una entrevista.** Un prompt no es una arquitectura. Si toda la inteligencia del producto está en una cadena de texto, no hay nada que revisar.

**Enfoque híbrido:** el LLM propone y el dominio valida. Descartado por complejidad innecesaria: si el dominio ya sabe generar un plan válido, que lo genere.

## Consecuencias

### Positivas

- **Reproducible y testeable.** Seis tests demuestran que el sistema entiende de running: rechaza un maratón en 6 semanas, respeta el 10 %, incluye descarga, aplica tapering.
- **Auditable.** Cada número del plan tiene una línea de código y un test detrás.
- **Extensible por diseño.** El patrón Strategy permite añadir una distancia nueva con una clase, sin tocar el resto (Open/Closed).
- **Habilita la regla estrella:** el sistema **se niega** a generar un plan inviable y propone una alternativa. Un LLM suelto casi siempre complace al usuario; el dominio no.
- Reduce el coste y la latencia: generar un plan es cómputo local, no una llamada al modelo.

### Negativas

- **Es la parte que más tiempo consume** del proyecto: una jornada completa frente a las dos horas que costaría delegarlo.
- Las reglas son **una simplificación** de la ciencia del entrenamiento. Un entrenador profesional consideraría más variables (historial de lesiones, VO₂ máx medido, disponibilidad de terreno). Esto se documenta explícitamente en lugar de fingir rigor absoluto.
- **Menos flexible ante peticiones raras.** Si alguien pide un plan para una carrera de 15K, el sistema no lo cubre; un LLM habría improvisado algo. Se acepta: cobertura acotada y correcta antes que cobertura ilimitada y no verificable.
- La fórmula de Riegel **sobreestima el rendimiento en distancias largas** para corredores con poca base. Se aplica un factor conservador en maratón y se marca como estimación.

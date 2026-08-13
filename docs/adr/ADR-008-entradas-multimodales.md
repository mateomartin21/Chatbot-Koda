# ADR-008 · Entradas multimodales, con el vídeo como alcance opcional

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

Koda nació como un chatbot **de voz**. Pero el usuario real no siempre puede hablar: está en la oficina, en el transporte público, o acaba de terminar una serie y le falta el aire. Una app de voz que solo acepta voz es frágil.

Además, Bedrock acepta imágenes de forma nativa en la Converse API, lo que abre casos de uso concretos de running con muy poco coste de implementación.

## Decisión

Cuatro modalidades de entrada por el **mismo** caso de uso (`procesar_mensaje`), con prioridades distintas:

| Modalidad | Estado |
|---|---|
| **Voz** | Núcleo |
| **Texto** | Obligatorio — ~1 h de trabajo |
| **Fotos** | Prioritario — el caso de uso estrella es leer la pantalla del reloj |
| **Vídeo** | **Opcional.** Solo si todo lo demás está cerrado el domingo |

El vídeo, si se hace, se resuelve extrayendo fotogramas con `ffmpeg` y tratándolos como imágenes, reutilizando la tubería ya existente.

## Alternativas consideradas

**Solo voz, como el enunciado literal.** Descartado: el enunciado dice "chatbot de voz conversacional", y la voz sigue siendo el núcleo. Añadir texto no lo contradice — lo hace usable. Y tiene un beneficio práctico decisivo: **si el evaluador abre la app sin permisos de micrófono, la demo sigue funcionando.**

**Mandar el vídeo completo al modelo.** Descartado: coste alto, latencia alta, soporte irregular. Extraer fotogramas da el 90 % del valor con el 20 % del trabajo, y reutiliza código ya escrito.

**Un endpoint distinto por modalidad** (`/api/voz`, `/api/texto`, `/api/imagen`). Descartado: multiplicaría la lógica de contexto y autorización. Un `MensajeEntrante` con campos opcionales mantiene una sola ruta que auditar.

## Consecuencias

### Positivas

- **Menos fricción, no más features.** Cada modalidad responde a un contexto de uso distinto del mismo usuario.
- La foto del reloj **elimina el registro manual de entrenamientos**, que es justo donde los usuarios abandonan este tipo de apps. Es la feature que se recuerda de una demo.
- El texto hace la lógica conversacional **testeable sin generar audio**, lo que acelera todo el desarrollo.
- Un único punto de entrada mantiene la autorización y el ensamblado de contexto en un solo sitio.

### Negativas

- **Superficie de ataque mayor.** Subir archivos exige validar tamaño, tipo real por *magic bytes*, re-encodear y **eliminar EXIF** (las fotos de móvil llevan coordenadas GPS: guardarlas sería una fuga de datos seria).
- **Coste variable y menos predecible.** Una imagen consume bastantes más tokens que una frase.
- **La extracción de datos desde una foto puede equivocarse.** Se mitiga con un umbral de confianza: por debajo de 0,7 Koda pregunta en lugar de registrar. Un sistema que sabe cuándo no está seguro es mejor que uno que se inventa datos con aplomo.
- **El vídeo es la peor relación valor/hora del proyecto** y es lo primero que se corta. Se asume conscientemente y se documenta en el Roadmap si no llega a tiempo.

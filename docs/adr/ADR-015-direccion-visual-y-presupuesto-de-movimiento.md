# ADR-015 · Una dirección visual propia y un presupuesto de movimiento

**Estado:** Aceptado
**Fecha:** 2026-08-14

## Contexto

La interfaz funcionaba pero se veía genérica: fondo casi negro neutro, un único
acento naranja, emoji como iconografía, tipografía del sistema, las respuestas del
modelo volcadas en un bloque de texto sin formato y ninguna animación más allá de
mostrar y ocultar elementos. En escritorio era una columna de 480 px flotando en
medio de una pantalla vacía.

Dos cosas obligan a decidir de verdad y no solo a "dar una pasada de CSS":

1. **La combinación de partida es exactamente el aspecto por defecto de una interfaz
   generada por IA.** Las guías de diseño que se consultaron (`frontend-design` de
   Anthropic, `taste-skill`) coinciden en identificar tres estéticas que aparecen
   *independientemente del tema del producto*, y una de ellas es "fondo casi negro
   con un único acento vermellón". No es que estuviera mal: es que no era una
   elección, era la ausencia de una.
2. **Los emoji no son parte del diseño de la app, son parte del teléfono de quien
   la abre.** 🎙️ lo dibuja Apple en un iPhone, Google en un Android y Microsoft en
   Windows, con tres formas y tres paletas distintas. Un producto que se evalúa por
   su acabado no puede dejar su iconografía en manos del sistema operativo.

También pesa la fecha: la prueba se entrega el 17 de agosto y se graba un vídeo de
demo. Lo que se ve es lo primero que se juzga.

## Decisión

**Se adopta una dirección visual anclada en el mundo del runner, se vendoriza toda
la tipografía e iconografía dentro del repo, y el movimiento se raciona por
frecuencia de uso en lugar de añadirse donde quepa.**

En cuatro partes:

### 1. Dirección: "la hora azul"

El fondo no es un gris de editor de código: es el índigo del cielo antes del
amanecer, que es cuando de verdad se entrena, y el acento es esa primera luz cálida.
Los dos colores dicen algo del sujeto en lugar de ser "oscuro + naranja". Los
colores de las sesiones (suave, largo, series, descanso) son los que usa cualquier
gráfica de zonas de running: son información, no decoración.

El elemento distintivo es **la pista**: el plan dibujado como una fila de carriles,
uno por semana, con la altura proporcional al volumen. La caída del final no hay que
explicarla — se ve que es el taper.

### 2. Tipografía y iconos vendorizados

- **Archivo** (variable, con eje de anchura) para lo que se lee.
- **DM Mono** para lo que se mide: ritmos, tiempos, distancias, fechas. Un dato no
  va nunca en la misma letra que una frase; se lee de un vistazo, se alinea en
  columna y no baila cuando cambia el número.
- **Phosphor** para los iconos, en un único sprite SVG.

Los tres archivos viven en el repo, no en un CDN. Licencias y tamaños en
[`app/interfaces/web/LICENCIAS-DE-TERCEROS.md`](../../app/interfaces/web/LICENCIAS-DE-TERCEROS.md).

### 3. Presupuesto de movimiento

Antes de animar algo se responden dos preguntas: **cuántas veces al día se va a ver**
y **qué problema resuelve**. Si no hay respuesta a la segunda, no se anima.

| Se ve | Qué se permite | Qué hay en Koda |
|---|---|---|
| Cientos de veces al día | Nada | La app no anima al abrir ni al enfocar el campo de texto |
| Decenas de veces | Casi imperceptible | Entrada de mensaje (220 ms), pulsación de botón (160 ms) |
| De vez en cuando | Animación normal | Cajones y hojas (420 ms), esqueletos de carga |
| Raro o la primera vez | Aquí va el presupuesto de deleite | Los carriles del plan creciendo en cascada |

Reglas que se aplican en todo: solo `transform` y `opacity`; nunca `ease-in` en la
interfaz; curvas fuertes en lugar de las flojas del navegador; nada entra desde
`scale(0)`; y `prefers-reduced-motion` se respeta reduciendo, no apagando.

Dos animaciones son **funcionales, no decorativas**, y por eso existen:

- Las barras de la grabación se mueven con el volumen real del micrófono. Si no se
  mueven, no te está oyendo — y eso se ve **antes** de mandar el audio.
- Cuando la transcripción provisional se sustituye por la confirmada, las dos se
  cruzan con un desenfoque de 2 px. Sin él se ven dos frases superpuestas; con él el
  ojo lee una sola que se afina.

### 4. El texto del modelo se formatea construyendo nodos

Las respuestas llegan en texto plano con guiones, listas numeradas y `**negritas**`.
Se interpretan y se pintan **nodo a nodo con `createElement`**, nunca con
`innerHTML`. Además, un detector de medidas pasa a la tipografía de datos lo que es
un ritmo, una distancia o un tiempo.

La razón de fondo no es estética: **lo que escribe un LLM no debe poder convertirse
nunca en HTML.** Si mañana alguien consigue que el modelo devuelva `<script>`, con
`innerHTML` sería XSS y con `createElement` es texto.

## Alternativas consideradas

**Cargar tipografías e iconos desde Google Fonts y un CDN.** Es lo normal y es una
línea de HTML. Se descarta porque mete dos dominios de terceros en el camino crítico
del primer render, porque la app deja de funcionar bien sin internet, y porque cada
carga le dice a un tercero quién está usando Koda. Vendorizar cuesta 130 KB una vez
y los quita a los tres.

**Usar Lucide o Feather para los iconos.** Es lo primero que se eligió, y se
descartó tras una auditoría que los señala como *la* elección por defecto de las
interfaces generadas por IA. Phosphor tiene además vocabulario del sujeto —
zapatilla en movimiento, bandera de meta, cronómetro — que Lucide no tiene.

**Dibujar los iconos a mano en SVG.** Se intentó y se abandonó: 30 iconos dibujados
a ojo no tienen el grosor de trazo ni el ritmo óptico consistentes, y se nota.

**Meter un framework (React, Svelte) para poder usar una librería de componentes.**
Se descarta sin discusión: [ADR-002](ADR-002-python-fastapi.md) ya decidió no usar
framework, la app es una pantalla con dos paneles, y cambiar de stack a tres días de
la entrega es la peor idea disponible.

**Ofrecer modo claro.** Se descarta a propósito. Un tema que se elige mal se ve mal
en la mitad de los casos; se prefiere una dirección comprometida y bien ejecutada.

## Consecuencias

### Positivas

- La interfaz ya no se puede confundir con una plantilla, y la identidad sale del
  sujeto (running, la hora a la que se entrena) y no de un catálogo.
- Cero peticiones a terceros y cero dependencias nuevas en `requirements.txt`. La
  interfaz sigue siendo HTML, CSS y JavaScript sin compilar.
- Los datos numéricos se leen de un vistazo y se alinean en columna.
- Las respuestas largas del modelo dejan de ser un muro: párrafos, listas y medidas
  destacadas.
- El formateo por nodos cierra un vector de XSS que `innerHTML` habría dejado
  abierto para siempre.
- En escritorio el plan es una columna fija: consultarlo deja de costar un clic.

### Negativas

- **La primera carga descarga 130 KB que antes no descargaba.** Con `font-display:
  swap` no bloquea, pero en una red lenta hay un instante con la letra del sistema.
- **Solo hay modo oscuro.** Quien tenga el sistema en claro va a ver Koda oscuro de
  todas formas, y no hay forma de cambiarlo.
- **El formateador es un subconjunto de Markdown escrito a mano.** Si el modelo
  devuelve tablas, encabezados o bloques de código, se ven como texto plano. Se
  aceptó porque el prompt pide respuestas conversacionales, pero es una promesa que
  el prompt puede romper sin avisar.
- **El detector de medidas es una expresión regular y no entiende el contexto.**
  Puede marcar como dato algo que no lo es. Falla en bonito, pero falla.
- **Hay dos rutas de maquetación** — cajón por debajo de 1200 px y columna anclada
  por encima — y las dos hay que probarlas. Es más superficie de la que había.
- **La verificación visual se hizo con capturas de Playwright fuera de la suite de
  tests.** No hay nada que impida una regresión visual: `pytest` seguiría en verde
  con la interfaz rota. Un test de regresión de imagen es trabajo real y no cabe
  antes del 17.
- **Las animaciones no se han probado en un móvil físico**, solo en un navegador de
  escritorio a tamaño de móvil. El desenfoque de la transcripción y el
  `backdrop-filter` de las hojas son justo lo que Safari en iOS ejecuta peor.

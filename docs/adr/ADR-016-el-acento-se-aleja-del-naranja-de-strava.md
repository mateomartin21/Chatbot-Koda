# ADR-016 · El acento se aleja del naranja de Strava

**Estado:** Aceptado
**Fecha:** 2026-08-14
**Supersede a:** [ADR-015](ADR-015-direccion-visual-y-presupuesto-de-movimiento.md)

## Contexto

[ADR-015](ADR-015-direccion-visual-y-presupuesto-de-movimiento.md) eligió el índigo
de la hora azul como fondo y un naranja amanecer (`#FB7A46`) como acento. La
dirección se sostiene; **el acento concreto no**, y salió al medirlo.

Se auditaron seis productos del mundo del running visitándolos con un navegador de
verdad y midiendo los estilos computados de los elementos que ocupan pantalla,
ponderados por área. No lo que dicen sus guías de marca: lo que pintan.

| Producto | Fondo | Acento | Tipografía |
|---|---|---|---|
| **Runna** *(propiedad de Strava)* | `#161616` | coral `#EC7159` + teal `#72BAAF` | Inter |
| **Strava** | blanco | `#FC5200` | Boathouse (propia) |
| **Whoop** | blanco / negro | `#4A53FF` | Proxima Nova |
| **Oura** | crema `#F7F1E8` | `#2A72DE` | Akkurat + Editorial New |
| **Gentler Streak** | blanco | `#FD6217` | Inter |
| **Hevy** | blanco | `#267FE8` | Inter |

Lo que aparece:

1. **Koda había aterrizado dentro de la familia Strava sin decidirlo.** Runna es el
   competidor funcional más parecido — planes de running algorítmicos —, es de
   Strava, su web es oscura y su llamada a la acción es `#EC7159`. El acento de
   Koda era `#FB7A46`. Prácticamente el mismo color sobre casi el mismo fondo. Eso
   no es convención de categoría: es parecerse al líder y a su filial.
2. **El hueco libre no era el azul.** Naranja lo tienen Strava y Gentler Streak;
   azul, Whoop, Oura y Hevy; teal, Runna.
3. **En tipografía Koda ya iba por delante.** Tres de las seis usan Inter, que es la
   fuente por defecto de todo.

## Decisión

**El acento pasa de naranja amanecer a oro (`#FFB43F`), y el presupuesto de
movimiento se amplía con seis animaciones más, cada una con su porqué.**

### 1. Paleta

| Papel | Antes | Ahora |
|---|---|---|
| Acento | `#FB7A46` | `#FFB43F` |
| Acento pulsado | `#EF6A34` | `#E8952A` |
| Realce | `#FFC46B` | `#FFD79A` |
| Semana de taper | oro claro | `#A5EDD2` |

El fondo, la tipografía, la iconografía y el resto de ADR-015 no cambian: el
concepto sigue siendo "la hora azul y la primera luz". Lo que cambia es que la
primera luz es **oro y no naranja rojizo** — que además es más fiel a la hora que
representa.

El taper se movió porque el oro pasó a ser el acento. Un taper **es una descarga**,
la última, así que ahora se pinta como una descarga más suave. Eso **quita** un
color del sistema en vez de añadir uno.

### 2. Seis animaciones más

Cada una pasó la misma puerta: cuántas veces al día se ve, y qué problema resuelve.

| Qué | Frecuencia | Para qué |
|---|---|---|
| Cambio de pantalla (entrar → app) | Una vez por sesión | Evitar que el contenido aparezca de golpe tras la redirección |
| Sugerencias del estado vacío, en cascada | Primera vez | Presupuesto de deleite |
| Tarjetas del plan, en cascada | Ocasional | Lo mismo, en una superficie que se abre a ratos |
| Ecualizador en el avatar de Koda | Mientras habla | Indicar estado: el anillo decía "algo pasa"; tres barras dicen "está sonando su voz" |
| Acordeón de las semanas | Ocasional | Evitar que el contenido se teletransporte |
| Arrastrar la hoja para cerrarla | Ocasional, en móvil | El asa promete que se puede empujar; tiene que cumplirlo |

Tres se **rechazaron**, y eso también es una decisión:

- **Contador de días animado.** Es el dato que el runner va a leer. Los datos que se
  leen no se mueven por estética.
- **Aparición de las semanas al desplazarse.** Se ven decenas de veces mientras se
  recorre el plan: ahí solo cabe lo imperceptible, o nada.
- **Animación al abrir la app.** Se ve cada vez que se entra.

### 3. Fondo de curvas de nivel

Las pantallas con sitio de sobra — entrar y el estado vacío — llevan un mapa de
curvas de nivel generado por [`scripts/generar_relieve.py`](../../scripts/generar_relieve.py),
teñido con una máscara CSS. Es como se dibuja una ruta con desnivel en cualquier
mapa o GPS: el fondo dice "running" sin una fotografía.

## Alternativas consideradas

**Verde de alta visibilidad** (`#CFF54A`), el del chaleco reflectante. Era el hueco
más vacío de la categoría y el más ligado al concepto — es lo que te pones para
correr a oscuras. Se descartó porque "fondo oscuro + verde ácido" es uno de los tres
aspectos que las guías de diseño marcan como típicos de una interfaz generada por
IA, y a tres días de la entrega no hay margen para equivocarse en esa apuesta.

**Dejar el naranja** y asumir el parecido como convención de categoría. Es defendible
— un runner reconoce naranja sobre oscuro al instante — y era la opción de riesgo
cero. Se descartó porque era la única parte del diseño que no salía del sujeto sino
de la inercia.

**Una fotografía de banco de un corredor al amanecer.** Se intentó: Unsplash y Pexels
bloquean la descarga automática, y Openverse solo devuelve fotografía amateur con
licencia dispar. Además, la auditoría de diseño marca la fotografía de banco como una
de las señales de una página hecha con plantilla. Las curvas de nivel resuelven lo
mismo — dar textura y contexto — sin licencia que respetar y con 21 KB.

**Un ilustrador o un modelo de imagen para dibujar la cara de Koda.** Es lo correcto
y no está hecho. Se evaluó usar el lobo de Fluent Emoji de Microsoft (licencia MIT,
bien dibujado) y se descartó: es gris y morado, choca con la paleta, y se reconoce al
instante como el emoji de Windows. Sería lo más prestado de toda la app.

## Consecuencias

### Positivas

- El acento ya no se confunde con el de Strava ni con el de Runna.
- El oro sobre índigo es más fiel a la hora que la dirección dice representar.
- El sistema de color tiene **un color menos**, no uno más.
- Las decisiones de color ahora se apoyan en medidas de productos reales, no en gusto.
- El movimiento cubre los momentos que faltaban: hablar, abrir, cerrar y desplegar.

### Negativas

- **El oro tiene menos contraste sobre el índigo que el naranja.** El texto oscuro
  encima se oscureció para compensar, pero el acento sobre fondo oscuro es ahora un
  poco menos legible para quien tenga baja visión. No se ha medido con una
  herramienta de contraste; se ha juzgado a ojo sobre capturas.
- **Un ADR de hace unas horas ya está superseded.** Es correcto según las reglas del
  repo, pero deja el historial con una decisión de color que duró medio día: la
  auditoría de la competencia debería haberse hecho *antes* de elegir la paleta, no
  después.
- **Ninguna de las seis animaciones nuevas se ha probado en un móvil físico.** La de
  arrastrar la hoja es precisamente la que depende del hardware: la captura del
  puntero y el multitáctil se comportan distinto en Safari de iOS.
- **El arrastre solo funciona desde la cabecera de la hoja.** Arrastrar desde el
  contenido pelearía con el desplazamiento, así que se limitó — pero un usuario que
  intente arrastrar desde el medio va a pensar que no funciona.
- **Koda sigue sin cara propia.** Tiene una marca, no un personaje, y eso es una
  carencia real de personalidad que este ADR no resuelve.
- **El fondo de curvas añade 21 KB** y, sobre todo, depende de `mask-image`, que en
  navegadores antiguos no existe: ahí el fondo simplemente no aparece. Degrada bien,
  pero degrada.

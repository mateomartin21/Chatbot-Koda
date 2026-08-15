# ADR-018 · Koda tiene cara, y la aplicación se instala en el móvil

**Estado:** Aceptado
**Fecha:** 2026-08-15

## Contexto

[ADR-016](ADR-016-el-acento-se-aleja-del-naranja-de-strava.md) dejó la dirección
visual cerrada: fondo nocturno, acento ámbar, iconos de línea de Phosphor. Lo que no
resolvió es que **la interfaz no tiene a nadie dentro**. El producto se llama Koda,
dice "Hola, soy Koda" y responde en primera persona, pero lo que hay junto a ese
texto es un icono de línea. La promesa de la portada — "háblale como a una persona" —
se cae en la primera pantalla.

Aparte hay un problema físico. El caso de uso es el móvil, y una pestaña del
navegador con la barra de direcciones encima no se parece a una aplicación por muy
bien resuelta que esté por dentro. En el vídeo de demo esa barra sale en todos los
planos.

Y hay un tercer asunto, pequeño y muy caro: **los cambios no se veían al recargar**.
Sin `Cache-Control`, el navegador se inventa uno — guarda el fichero un 10% del
tiempo que lleva sin modificarse — y un `app.js` tocado hace tres días se queda
cacheado siete horas. Durante ese rato, lo desplegado y lo que se ve dejan de ser lo
mismo, con toda la pinta de un bug del servidor.

## Decisión

### 1. El personaje aparece en cuatro sitios, y en ninguno más

| Sitio | Gesto | Por qué ahí |
|---|---|---|
| Tarjeta de entrar | Neutro | Es la primera impresión y no compite con nada |
| Cabecera del chat | Neutro, cambia al fallar | Dice **con quién** estás hablando |
| Bienvenida | Contento | Acompaña a "Hola, soy Koda" |
| Cierre de la portada | Corriendo | Después de las capturas, no antes |

Deliberadamente **no** va en el avatar de cada mensaje, que sigue con el icono de
línea. A 28 px el dibujo es una mancha, y repetido veinte veces en una conversación
deja de significar nada. El avatar por mensaje resuelve "quién dijo esto"; para eso
un icono es mejor que un retrato.

Tampoco va en el rail ni en el pie: ahí manda el logotipo. **Logotipo y personaje son
cosas distintas** — uno identifica al producto y se tiñe con `currentColor`, el otro
identifica a quien te contesta. Por eso no comparten clase CSS.

### 2. El único gesto que se dispara es el de fallar

La cara de la cabecera cambia a la de duda cuando una petición se cae, y vuelve sola
a los tres segundos. No sonríe al acertar ni celebra nada.

La queja de siempre de una interfaz de chat es que **un error se lee igual que una
respuesta**: mismo color, misma burbuja, mismo sitio. El gesto lo hace evidente sin
un cartel rojo. Un personaje que reacciona a todo se convierte en ruido y deja de
avisar de nada.

### 3. Los recortes los hace un script, no un editor de imágenes

`scripts/recortar_mascota.py` toma la hoja de personaje entera y saca cada pose ya
sin fondo, al tamaño en el que se usa. El arte original va en el repositorio en WebP
sin pérdida — pesa la mitad que el PNG — porque **sin él, el script sería
documentación en vez de una herramienta**.

Quitar el fondo tiene truco y está comentado en el propio script: el fondo es un
degradado, así que la región crece comparando contra el píxel vecino y no contra un
color fijo; se para en un muro de luminancia, que es el contorno claro de cada pose;
y al final se queda solo con la mancha grande, porque las poses están pegadas en la
hoja y siempre entra una esquirla de la vecina.

### 4. La aplicación se instala: `manifest.webmanifest` con `start_url: /app/`

Añadida al inicio, Koda abre a pantalla completa, sin barra de direcciones, con su
icono. `start_url` apunta a `/app/` y **no** a la raíz: tocar el icono tiene que
llevar al chat, no a la página de marketing. Hay un test que lo comprueba.

### 5. Los estáticos se revalidan siempre; las tipografías, nunca

`Cache-Control: no-cache` en todo menos en las fuentes, que van con `immutable` a un
año. `no-cache` no es "no lo guardes", es "guárdalo, pero pregunta antes de usarlo":
como ya se manda `ETag`, la pregunta se contesta con un 304 vacío.

## Alternativas consideradas

**Dejar solo el icono de línea y no meter personaje.** Es lo más seguro para una
prueba técnica: un lobo de dibujos puede leerse como poco serio. Se descarta porque
el producto entero se apoya en que hablas con alguien, y la parte de la evaluación
que mira producto — no solo código — habría visto una promesa incumplida en la
primera pantalla. El riesgo se acota manteniendo el dibujo fuera del contenido: no
aparece dentro de ninguna respuesta ni junto a ningún dato.

**Ilustración también en el hero de la portada.** Se descarta: arriba el argumento es
"esto existe y funciona", y eso lo sostienen las capturas reales. Un dibujo compitiendo
con ellas debilita justo lo que hay que demostrar. Abajo, con el visitante ya
convencido, no molesta.

**Una animación continua en el personaje** (respirar, mover la cola). Sale del
presupuesto de movimiento de [ADR-015](ADR-015-direccion-visual-y-presupuesto-de-movimiento.md):
movimiento permanente sin nada que comunicar, en una pantalla donde se lee texto.

**Service worker y modo sin conexión.** Es el paso siguiente natural del manifest y
se descarta por alcance: Koda sin red no puede hacer nada útil — todas sus respuestas
vienen de un modelo remoto — así que una caché offline serviría para enseñar la
conversación vieja y poco más. Y un service worker mal invalidado es la forma más
rápida de recrear justo el problema de caché que este ADR arregla.

**Versionar los estáticos con un hash en el nombre** (`app.a3f9.js`) y cachearlos un
año. Es lo correcto con tráfico de verdad y evita el viaje de revalidación. Necesita
un paso de compilación que este proyecto no tiene, y montarlo para cuatro ficheros
estáticos es más máquina que problema.

## Consecuencias

### Positivas

- La primera pantalla cumple lo que promete la portada.
- Un fallo de red se distingue de una respuesta sin añadir un color de alerta.
- Instalada, la aplicación no enseña barra de direcciones: el vídeo de demo se graba
  sin que salga el navegador.
- Los recortes se pueden rehacer con un comando si el arte cambia.
- Un despliegue se ve al recargar, siempre. Esto, en una demo, vale más que los
  milisegundos que cuesta.

### Negativas

- **El estilo del personaje no lo controla el proyecto.** Es arte generado y ajustado
  a mano una vez; si hiciera falta una pose nueva no hay forma de producirla en el
  mismo estilo con garantías. Cualquier ampliación del personaje depende de volver a
  la misma herramienta y tener suerte.
- **Un lobo de dibujos es una apuesta de tono.** Encaja con Koda; en un producto
  clínico o corporativo sería un error. La decisión es del proyecto, no una regla
  general, y quien la evalúe puede no compartirla.
- **El recorte automático deja restos.** La pose corriendo conserva una sombra tenue
  detrás de la cola: invisible sobre el fondo nocturno, visible sobre uno claro. Estas
  imágenes solo sirven sobre fondo oscuro.
- **Los umbrales del recorte están afinados para esta hoja concreta.** Con otro arte
  habría que volver a tocarlos mirando el resultado; el script no los deduce.
- **Cada estático cuesta ahora un viaje de revalidación**, incluidas las imágenes del
  personaje. Con un usuario no se nota; es una decisión pensada para una demo, no para
  tráfico real.
- **La instalación solo funciona sobre HTTPS.** En local no se puede probar más que en
  `localhost`, así que hasta el despliegue esto está escrito pero sin verificar en un
  móvil de verdad.
- **2 MB de arte original en el repositorio.** Es el precio de que el script sea
  ejecutable y no un adorno.

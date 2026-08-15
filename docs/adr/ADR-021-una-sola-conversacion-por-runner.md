# ADR-021 · Una sola conversación por runner, que sobrevive a cerrar la pestaña

**Estado:** Aceptado
**Fecha:** 2026-08-15

## Contexto

El hilo de la conversación se guardaba desde el primer día — es de donde sale la
ventana corta de la memoria ([ADR-005](ADR-005-memoria-tres-capas.md)) — pero **solo
lo leía el modelo**. La persona cerraba la pestaña, volvía, y se encontraba "Hola, soy
Koda" y una pantalla en blanco, mientras por dentro Koda se acordaba de su rodilla.

Esa contradicción es peor que no tener memoria: parece que se le olvidó. Y como la
memoria es la mitad de la tesis del proyecto, es justo lo que no se puede parecer.

Al arreglarlo aparece la pregunta de al lado: **¿debería un runner poder tener varias
conversaciones**, como en cualquier chat de IA, en vez de un único hilo?

## Decisión

### 1. Al abrir, se pinta lo último que os dijisteis

`GET /api/conversacion` devuelve los **40 últimos mensajes** del runner del JWT, y la
aplicación los pinta antes que nada. Si hay historial, la bienvenida no aparece.

40 y no 10 —el tamaño de la ventana del modelo— porque son cosas distintas: la ventana
es lo que el modelo necesita para no perder el hilo; esto es lo que una **persona**
necesita para reconocer de qué estaban hablando, y para eso hace falta ver más. Sigue
siendo un tope: quien lleve un año usando Koda no se descarga su historial entero cada
vez que abre la pestaña.

Entre días distintos va un separador con "Hoy", "Ayer" o la fecha. Sin él, una
conversación de hace tres semanas se lee como si acabara de pasar, y un "te veo el
martes" de entonces confunde.

El historial no entra con animación. Cuarenta mensajes animándose a la vez serían
medio segundo de cascada antes de poder leer nada, y además sería mentir: no está
llegando ahora, ya estaba.

Si la petición falla, se enseña la bienvenida y no se dice nada. Perder el historial
es molesto; no poder escribir es descalificante.

### 2. Una sola conversación por runner. No hay hilos.

Y no es una simplificación por falta de tiempo: es lo que corresponde a este producto.

**La memoria de Koda es de la relación, no del hilo.** Las tres capas del ADR-005 —
perfil, ventana corta, hechos duraderos — describen a *una persona*, no a *una
conversación*. Partirla en hilos obliga a contestar preguntas que no tienen buena
respuesta: si le cuentas lo de la rodilla en el hilo A, ¿lo sabe el hilo B? Si lo sabe,
los hilos no están separados y la interfaz miente. Si no lo sabe, Koda tiene amnesia
selectiva según dónde le hables, que es exactamente el fallo que este ADR arregla.

**El dominio tampoco se divide.** Hay un plan activo, un perfil, un calendario. Todos
los hilos hablarían de lo mismo, y la pregunta "¿en cuál pedí el plan?" no debería
existir.

**Y es la metáfora equivocada.** Los hilos son de una herramienta de trabajo, donde
cada conversación es una tarea que empieza y acaba. Koda no es eso: nadie tiene la
"conversación 3" con su entrenador. Es una relación que continúa, y una sola línea de
tiempo es lo que la representa.

## Alternativas consideradas

**Varias conversaciones por runner, con lista lateral.** Es lo que espera cualquiera
que use un chat de IA, y por eso la pregunta es legítima. Se descarta por lo de arriba
—rompe el modelo de memoria y no hay nada que separar— y, en segundo lugar, por
alcance: haría falta una tabla nueva, un enrutado por hilo, una lista en la interfaz y
reabrir el ADR-005 para que el contexto sea consciente del hilo. Quedan dos días.

Reconsiderar si algún día Koda lleva **varios atletas por cuenta** (un entrenador con
sus clientes) o **varios objetivos a la vez**. Entonces sí habría algo que separar, y
serían atletas u objetivos, no "chats".

**Empezar hilo nuevo al crear un plan nuevo.** Suena razonable —una temporada, una
conversación— y se descarta por lo mismo: lo que le contaste de tu rodilla no caduca
cuando cambia el objetivo. Lo que sí caduca son los hechos, y de eso ya se encarga la
capa de memoria.

**Que el runner pueda borrar el historial.** No se descarta, se pospone: no está
construido. Ver consecuencias.

**Caducar las conversaciones a los N días.** Sería una política de retención honesta,
pero borrar el hilo se llevaría por delante la ventana corta y con ella la sensación
de continuidad — justo lo que se acaba de arreglar. Se prefiere guardarlo todo y
acotar lo que se *lee*.

## Consecuencias

### Positivas

- Cerrar la pestaña deja de ser empezar de cero. La memoria que Koda ya tenía por
  dentro ahora también se ve.
- La continuidad se puede **enseñar** en el vídeo de demo sin hablar de la base de
  datos: cierras, vuelves a entrar, y la conversación sigue ahí.
- El coste es acotado y constante: 40 mensajes por apertura, con índice por
  `runner_id` y fecha.
- No hay una interfaz de hilos que mantener, ni una decisión de "en qué hilo va esto"
  que el runner tenga que tomar cada vez.
- El aislamiento entre runners tiene su propia suite: es la ruta más sensible de la
  API — el plan son números, la conversación es lo que la persona escribió.

### Negativas

- **El historial no se puede borrar.** No hay forma de que un runner elimine lo que
  contó, ni desde la interfaz ni desde ningún sitio. Para un dato tan personal como
  una conversación sobre lesiones, eso es una carencia real y no solo una función que
  falta.
- **Crece sin límite.** Nada purga la tabla `conversaciones`. Con un usuario da igual;
  con tráfico real haría falta una política de retención que hoy no existe.
- **Se cargan 40 mensajes en cada apertura**, aunque el runner solo entre a mirar su
  plan. Es una petición y unos kilobytes, pero es trabajo que muchas veces no se usa.
- **No hay paginación**: lo anterior a esos 40 mensajes es inalcanzable desde la
  interfaz aunque siga en la base de datos.
- **Un runner que vuelva a los seis meses** ve su última conversación como si fuera lo
  siguiente que toca. El separador de fecha lo avisa, pero no lo resuelve.
- **Si alguien esperaba varios chats, no los va a encontrar**, y la razón vive en este
  documento y no en la interfaz.

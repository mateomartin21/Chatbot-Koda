# ADR-020 · Nova Sonic habla, el modelo grande decide

**Estado:** Aceptado
**Fecha:** 2026-08-15

## Contexto

[ADR-011](ADR-011-nova-sonic-y-gateway-de-modelos.md) puso Nova Sonic delante de la
conversación hablada y le dio las cinco herramientas del coach. La latencia mejoró
como se esperaba: de 3–5 segundos a medio segundo. Lo que no se anticipó es lo que
pasa cuando un modelo pequeño de tiempo real tiene que **decidir**.

Estas tres conversaciones son reales, todas del 14 de agosto:

**Una.** El runner pide un maratón que no da tiempo. El dominio lo rechaza y propone
un 21K. El runner dice "sí, créame ese plan". Koda repite la misma frase. Otra vez. Y
otra. Tres veces seguidas.

**Dos.** Arreglado lo anterior desde el prompt, aparece lo de debajo: Koda propone "un
21K" sin decir la fecha, el runner acepta, y Koda le pregunta cuándo quiere correr —
una fecha que le habían dicho dos frases antes.

**Tres.** Arreglado también, queda esto: el runner dice "sí, créame el plan para el
veinte de noviembre" — repitiendo la **fecha** pero no la **distancia** — y el modelo
vuelve a llamar a `crear_plan` con el maratón. Solo entra cuando dice "veintiún k".

Las tres tienen la misma forma: **no razona mal, se le cae el estado**. Con una frase
ambigua y diez turnos de contexto, elige mal el argumento. Y las frases ambiguas son
la mayoría de cómo habla la gente.

Cada arreglo por prompt mejoró el caso concreto y destapó el siguiente. Eso ya no es
afinar: es sostener a un modelo en una tarea que no le toca.

Hay además un problema que no se había mirado de frente. Nova Sonic recibía el
contexto entero del runner — su plan, sus ritmos, sus hechos de memoria — porque hacía
falta para que contestara. **Un modelo con los ritmos del runner en el contexto puede
decir un ritmo equivocado.** Nada lo impedía.

## Decisión

**Nova Sonic deja de ser el coach y pasa a ser su voz.**

### 1. Una sola herramienta

En voz, Nova Sonic ya no recibe `crear_plan`, `consultar_plan`,
`guardar_datos_del_runner`, `configurar_recordatorio` ni `registrar_entrenamiento`.
Recibe **una**: `preguntar_al_entrenador(peticion)`.

Detrás de esa llamada hay una conversación entera con el modelo grande — el mismo
gateway que atiende `POST /api/mensajes`, con el contexto completo, las cinco
herramientas de verdad y el dominio debajo. El modelo grande decide y ejecuta; Nova
dice el resultado en voz alta.

### 2. Nova no recibe ni un dato del runner

Su prompt (`app/prompts/voz_locutor.md`) no contiene el plan, ni los ritmos, ni el
perfil, ni la memoria, ni siquiera la fecha de hoy. Dice cómo hablar y a quién
preguntárselo todo.

**Esta es la garantía, y es estructural.** No se le pide a un modelo que no invente:
se le quita aquello con lo que podría inventar. Un modelo que no tiene un ritmo en el
contexto no puede decir un ritmo equivocado — como mucho puede callarse. Es el mismo
criterio con el que `Imagen` solo la construye el saneador
([ADR-017](ADR-017-la-foto-se-reprocesa-antes-de-salir.md)) y con el que el gateway se
salta los modelos que no ven.

Hay un test que lo fija. Si alguien vuelve a meterle el contexto a Nova Sonic para
que conteste más rápido, se cae.

### 3. Si cierra un turno sin consultar, el turno se rehace

El servidor sabe si la herramienta se llamó. Si no se llamó y el runner había dicho
algo, se consulta al entrenador desde el servidor con lo que dijo y la respuesta buena
se manda al hilo.

No se puede retirar lo que Nova ya dijo — el audio sonó. Pero como su prompt está
vacío de datos, lo peor que puede haber dicho es una frase de relleno, y detrás llega
la respuesta de verdad. **Lo que no puede pasar es que el runner pregunte y se quede
sin respuesta creyendo que le contestaron**, que es tan malo como una inventada.

### 4. Tres prompts, tres papeles

| Fichero | Quién lo lee | Qué es |
|---|---|---|
| `coach_system.md` | el modelo grande, por escrito | el coach entero |
| `coach_voz.md` | el modelo grande, cuando la petición llegó hablando | el mismo coach, con respuestas cortas y sin markdown |
| `voz_locutor.md` | Nova Sonic | cómo hablar, y nada más |

## Alternativas consideradas

**Seguir afinando el prompt de Nova Sonic.** Es lo barato y ya se hizo tres veces:
cada arreglo mejoró su caso y destapó el siguiente. Se descarta porque el problema no
es qué le decimos, es a quién se lo pedimos.

**Volver a la cascada entera** (transcribir → modelo → sintetizar) y jubilar Nova
Sonic. Resuelve todo de un plumazo, y con la ventaja de que el modelo grande habla
directamente: sin paráfrasis de por medio, los números salen exactos. Se descarta
porque devuelve todos los turnos a 3–5 segundos, que es exactamente de donde venía el
ADR-011. Se conserva como el fallback que ya era.

**Enrutar por intención**: Nova contesta la charla y solo delega lo que toca una
herramienta. Sería lo mejor de los dos, y falla por lo mismo que todo lo demás —
decidir si algo toca una herramienta es justo la decisión que no sabe tomar.

**Forzar la llamada a la herramienta en la API.** Sería la garantía perfecta: que el
modelo no pueda contestar sin consultar. La Converse API de Bedrock tiene `toolChoice`,
pero la API de streaming bidireccional de Nova Sonic no expone un equivalente en
`toolConfiguration`. Por eso la garantía se construye quitándole los datos y
rescatando el turno, en vez de prohibiéndoselo.

**Dejar que Nova lea literalmente lo que devuelve el entrenador**, sin parafrasear. No
hay forma de pedírselo: la respuesta de una herramienta es entrada para el modelo, no
un guion. Se mitiga con la regla explícita de no cambiar números, fechas ni nombres.

## Consecuencias

### Positivas

- Las decisiones las toma el modelo que sabe tomarlas. Las tres conversaciones del
  contexto dejan de ser posibles por construcción, no por prompt.
- **Nova Sonic ya no puede inventarse un dato del runner porque no tiene ninguno.**
- Un turno sin consultar deja de ser silencioso: se detecta, se registra y se rehace.
- El contexto se arma en cada consulta y no al abrir la sesión, así que es más fresco:
  antes se congelaba al principio del turno.
- Hablar y escribir siguen siendo el mismo Koda — ahora de forma más literal que
  antes, porque detrás hay el mismo cerebro y las mismas herramientas.
- Nova Sonic sigue haciendo lo que hace muy bien: oír y hablar rápido.

### Negativas

- **Los turnos con herramienta pasan de ~0,5 s a 2–3 s.** Se recupera parte de la
  latencia que el ADR-011 fue a buscar. La charla sin herramienta sigue rápida, pero
  la mayoría de los turnos útiles llevan herramienta.
- **Dos llamadas a modelo por turno**, así que el coste por conversación sube y hay
  un punto más donde algo puede caerse.
- **Nova parafrasea lo que le devuelve el entrenador**; no lo lee literal. Es un salto
  más donde un número puede torcerse, y la única defensa es una regla en el prompt.
  No se ha medido con qué frecuencia falla.
- **Que Nova llame a la herramienta no está garantizado por la API**, solo por su
  prompt y por el rescate. El rescate llega tarde: el runner ya oyó la frase de
  relleno.
- **El rescate puede sonar raro.** Su texto se añade detrás de lo que dijo la voz, no
  en su lugar, así que en el hilo pueden quedar dos frases seguidas del coach.
- **Nova ya no sabe de qué se venía hablando.** Los pronombres ("¿y ese día qué
  hago?") los resuelve el modelo grande a partir de la conversación guardada, que es
  donde deben resolverse — pero si esa memoria fallara, la voz no tiene con qué
  arreglarlo.
- **Nada de esto se ha probado contra Nova Sonic de verdad.** Está construido y
  cubierto con dobles; que el modelo real llame siempre a su única herramienta es una
  promesa hasta que se pruebe hablando.
- **ADR-011 queda a medias.** No se supersede — el gateway de modelos, el fallback a
  la cascada y la elección de Nova Sonic siguen vigentes — pero su premisa de que la
  voz en tiempo real podía ser también el coach, no.

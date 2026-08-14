# ADR-013 · Un prompt propio para el modelo de voz

**Estado:** Aceptado
**Fecha:** 2026-08-14

## Contexto

[ADR-011](ADR-011-nova-sonic-y-gateway-de-modelos.md) dio por resuelta la objeción "no
hay punto donde insertar la lógica de dominio" porque Nova Sonic soporta *tool use*. Al
implementarlo de verdad — tres herramientas: crear plan, consultar plan y guardar el
perfil — aparecieron tres comportamientos que no se deducen de la documentación. Los tres
costaron una ronda de depuración con el producto delante.

### 1. El `toolResult` no se puede mandar al recibir el `toolUse`

Hay que esperar al `contentEnd` del bloque `TOOL`. Contestando antes, Nova Sonic responde
`ValidationException: Tool Response parsing error` y **tira la sesión con la herramienta
ya ejecutada**: el plan quedaba creado en la base de datos y el runner sin respuesta,
mientras el frontend caía a la cascada y creaba el plan otra vez.

El mensaje de error apunta al formato del contenido y despista: el formato era correcto,
lo que estaba mal era el momento. Se perdió una ronda entera persiguiendo el JSON.

### 2. El esquema de la herramienta viaja como cadena, no como objeto

En la Converse API del mismo Bedrock, `inputSchema` es `{"json": {...}}` con el esquema
como objeto. En Nova Sonic es `{"json": "{...}"}`, con el esquema **serializado a texto**.
Mismo servicio, misma cuenta, dos convenciones.

### 3. Ignora instrucciones que tiene escritas delante

Con el prompt de texto (~2 800 caracteres, escrito para Claude), Nova Sonic:

- preguntaba en qué año era una fecha, teniendo `Hoy es jueves 13 de agosto de 2026` en la
  primera línea del prompt;
- volvía a pedir los días disponibles que estaban dos líneas más abajo;
- no relacionaba la respuesta del runner con su propia pregunta anterior, aun teniéndola
  en la ventana de conversación.

No es aleatorio ni es un bug: es un modelo pequeño optimizado para latencia, y su
seguimiento de instrucciones se degrada con la longitud del prompt. Claude, con **el mismo
prompt y las mismas herramientas**, se comportaba correctamente.

## Decisión

1. **Dos prompts para el mismo coach.** `coach_system.md` (~2 800 caracteres) para el
   camino de texto; `coach_voz.md` (~900) para Nova Sonic. Dicen lo mismo; el segundo lo
   dice en un tercio del espacio y en imperativo.
2. **El contexto va delante del prompt largo, no detrás.** Al final se ignoraba.
3. **Las herramientas se diseñan para que el fallo no quepa.** La fecha de la carrera
   dejó de ser un campo `"AAAA-MM-DD"` y pasó a ser `dia` y `mes` obligatorios más `anio`
   opcional. Con un solo campo con formato, el modelo se sentía obligado a averiguar el
   año y lo preguntaba — tres intentos por prompt no lo evitaron. Partido, la pregunta
   deja de tener sentido porque no hay hueco que rellenar.

El punto 3 es el que generaliza: **pedirle a un modelo que no se equivoque aguanta peor
que diseñar la interfaz para que la equivocación no quepa.** Es la misma lógica por la que
ninguna herramienta recibe `runner_id`.

## Alternativas consideradas

**Un solo prompt, insistiendo más.** Es lo que se intentó primero: instrucción en el
system prompt, luego en imperativo y en mayúsculas, luego en la descripción de la
herramienta. Tres intentos, tres fracasos. Seguir era hacer lo mismo esperando otro
resultado.

**Acortar el prompt compartido para los dos modelos.** Habría evitado la duplicación, pero
paga el recorte donde no hacía falta: Claude sí usa los matices de carácter, el manejo de
temas fuera de alcance y las reglas de estilo hablado. Empobrecer el camino de texto para
arreglar el de voz es resolver el problema en el sitio equivocado.

**Devolver el texto a la cascada** y dejar Nova Sonic solo para el micrófono. Descartado:
la unificación fue una petición explícita y se nota — la voz y la latencia son las mismas
escribas o hables.

## Consecuencias

### Positivas

- Nova Sonic crea planes hablando, sin preguntar el año, verificado contra el modelo real:
  `crear_plan({"mes": 12, "dia": 15, "distancia_km": 42.0})`.
- El prompt de voz baja de 4 048 a 2 300 caracteres **contando ya el contexto**, así que
  la proporción de prompt que es información útil sobre el runner sube mucho.
- Cada prompt se puede afinar para su modelo sin miedo a estropear el otro.

### Negativas

- **Dos prompts que pueden divergir.** Es el riesgo real: se corrige una regla en uno y se
  olvida en el otro, y entonces hay dos Kodas con criterios distintos según escribas o
  hables. No hay test que lo detecte — los prompts no son deterministas. Mitigación pobre
  pero honesta: los dos viven en `app/prompts/` y se leen juntos.
- **El Koda de voz es un coach algo más simple.** Se quedaron fuera los matices de carácter
  y parte del manejo de temas fuera de alcance. Se notará si alguien intenta desviar la
  conversación hablando.
- **El prompt caching de Bedrock acierta menos.** Al llevar el contexto delante, el prefijo
  ya no es idéntico entre usuarios: sigue acertando entre mensajes de una misma
  conversación, que es de donde salen casi todos los aciertos, pero es coste real a cambio
  de que el modelo haga caso.
- **Estos tres comportamientos son de una versión concreta** de un modelo pre-1.0. Pueden
  cambiar sin aviso, y entonces habrá código defensivo que ya no protege de nada y nadie
  sabrá por qué está.
- Se sigue **sin poder testear nada de esto automáticamente**: todo se verificó a mano
  contra el modelo real y leyendo logs del servidor.

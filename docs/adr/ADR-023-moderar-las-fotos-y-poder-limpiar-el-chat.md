# ADR-023 · Moderar las fotos, y poder limpiar el chat sin perder la memoria

**Estado:** Aceptado
**Fecha:** 2026-08-16

## Contexto

Koda se probó con gente que no era su autor, y salieron dos huecos que no se ven
cuando uno prueba su propia aplicación.

**Las fotos.** Koda pide la pantalla de un reloj. Nada impide mandar otra cosa, y una
aplicación pública cuyo enlace se comparte va a recibir, antes o después, algo que no
es un reloj. Lo que ya había: la foto se sanea en el borde
([ADR-017](ADR-017-la-foto-se-reprocesa-antes-de-salir.md)) y **no se guarda en ningún
sitio** — ni en la base de datos, ni en S3, ni en disco. Eso deja fuera el riesgo
grande, que es alojar contenido ilegal. Lo que no había: ningún criterio propio. La
única barrera contra una foto sexual era que Claude se negara a describirla, y esa es
la barrera **de otro**: si Bedrock cambia sus filtros, el comportamiento de Koda cambia
sin que nadie toque una línea.

**El chat.** No existía forma de vaciarlo. Los mensajes se acumulaban para siempre y el
runner no podía borrar los suyos. En una aplicación que guarda datos personales, un
dato que entra y no sale no es un detalle de producto.

## Decisión

### 1. Un puerto de moderación, con Rekognition detrás

`ModeracionImagenPort` con un método, `revisar(imagen) -> Veredicto`. El adaptador
llama a `DetectModerationLabels` de Amazon Rekognition y se queda con las categorías de
primer nivel, que son las estables entre versiones del modelo.

Se revisa **después del saneado y antes de la llamada al modelo**. Ese orden importa:
saneado primero porque a partir de ahí nadie maneja los bytes que subió el navegador, y
antes del modelo porque una foto rechazada no debería costar dinero.

**Al runner no se le dice qué categoría saltó.** Se le contesta que esa foto no se puede
mirar y se le ofrece la alternativa. Decirle "rechazado por desnudos explícitos" es
escribirle el manual para esquivarlo; el motivo va al log, que es donde sirve.

### 2. Si la moderación no puede decidir, la foto pasa

Un fallo de Rekognition —servicio caído, permiso que falta, timeout— devuelve "apta" y
deja una advertencia en el log.

Es la decisión incómoda de este ADR y va razonada. Fallar cerrado significa que **cada
foto de reloj deja de funcionar** cuando un servicio auxiliar tiene un mal día: se rompe
la función de verdad, la que usa todo el mundo, para protegerse de un caso raro. Y lo
que se deja pasar en ese hueco no queda alojado en ningún sitio y sigue teniendo
enfrente los filtros del modelo. El estado degradado es exactamente el estado que Koda
tenía antes de este ADR, no uno peor.

### 3. Limpiar el chat borra la capa 2, y solo la capa 2

`DELETE /api/conversacion` vacía el hilo del runner del JWT. **No toca el perfil ni los
hechos duraderos** de [ADR-005](ADR-005-memoria-tres-capas.md).

"Limpiar el chat" y "olvida lo que te conté" son dos cosas distintas, y quien pulsa lo
primero casi nunca quiere lo segundo: quiere la pantalla en blanco, no volver a explicar
desde cero que le molesta la rodilla. Confundirlas convierte un botón de limpieza en una
pérdida de datos que el usuario no pidió.

Por eso la interfaz **lo dice antes de que se pulse**: que se borran los mensajes y que
el perfil, el plan y lo aprendido se quedan. Un usuario que borra el chat esperando que
Koda olvide su lesión, y descubre que la recuerda, se siente engañado con razón.

La confirmación es en dos pasos —el botón se convierte en su propia advertencia y hay
que pulsarlo otra vez— en lugar de un `confirm()` del navegador. Un diálogo nativo se
acepta por reflejo.

## Alternativas consideradas

**Dejar la moderación en manos de Bedrock.** Es lo que había, funciona razonablemente y
cuesta cero. Se descarta porque es una garantía prestada: no está bajo control, no deja
rastro propio y no evita pagar la llamada.

**Moderar con el propio modelo,** mandándole la foto y preguntándole si es apropiada.
Cuesta lo mismo que la llamada que se quería evitar, y le pide a un modelo de lenguaje un
trabajo de clasificación para el que existe un servicio dedicado más barato y más rápido.

**Bloquear cuando la moderación falla.** Más seguro sobre el papel. Se descarta por lo
del punto 2: convierte cualquier incidencia de un servicio auxiliar en una caída de la
función principal.

**Guardar las fotos rechazadas para poder revisarlas.** Tentador para auditoría y
exactamente lo contrario de lo que conviene: obliga a alojar justo el contenido del que
uno quiere no ser responsable.

**Que limpiar el chat borre también los hechos.** Más simple de explicar y peor: tira
información que costó varias conversaciones reunir, para resolver un problema que era
visual.

**Un borrado total de la cuenta.** Es lo correcto a futuro y es otra cosa: implica
tokens, planes, recordatorios y el propio runner. Queda fuera, anotado abajo.

## Consecuencias

### Positivas

- Koda tiene criterio propio sobre lo que mira, en vez de depender del de su proveedor.
- Una foto rechazada no cuesta una llamada al modelo.
- El puerto vuelve a demostrar para qué existe: cambiar Rekognition por otro servicio, o
  apagar la moderación entera, es una variable de entorno.
- El runner puede vaciar su conversación, y sabe exactamente qué desaparece.
- El borrado lleva `runner_id` en la firma del repositorio, así que no se puede llamar
  sin él — la misma frontera que el resto del proyecto.

### Negativas

- **Rekognition necesita un permiso que el usuario `koda-dev` no tiene.** Hasta que se
  añada `rekognition:DetectModerationLabels`, la moderación deja pasar todo y solo lo
  registra: funciona igual que si no existiera, y solo el log lo delata.
- **Cuesta dinero por imagen** (~1 USD por cada mil). Es poco, pero es un coste nuevo en
  el camino de cada foto.
- **Fallar abierto es una decisión con filo.** Durante una caída de Rekognition, Koda se
  comporta como antes de este ADR. Está razonado, no deja de ser un hueco.
- **Rekognition se equivoca.** A 80 de confianza el balance es razonable, pero una foto
  legítima puede caer, y el runner solo verá que no se la miran. No hay forma de apelar.
- **La moderación solo mira imágenes.** Lo que se escribe o se dice por voz no pasa por
  ningún filtro propio.
- **Limpiar el chat no borra los hechos, y eso puede confundir** a quien esperaba
  empezar de cero por mucho que el texto lo explique.
- **No hay borrado de cuenta.** Un runner puede vaciar su conversación pero no
  desaparecer del todo. Es el siguiente paso y hoy no está.
- **El borrado no es reversible ni deja registro.** Si alguien lo pulsa por error, no
  hay papelera.

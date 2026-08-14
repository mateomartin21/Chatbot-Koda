# ADR-012 · Cómo se resuelven las tensiones entre las reglas de entrenamiento

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

[02-DOMINIO-RUNNING](../contexto/02-DOMINIO-RUNNING.md) define ocho reglas (R1–R8) como si
fueran independientes. Al implementarlas resultó que **tres pares se contradicen** cuando
se aplican literalmente. No es un fallo de la documentación: cada regla es correcta por
separado, y es el hecho de escribirlas en código determinista lo que obliga a decidir cuál
cede. Un LLM generando planes en prosa nunca habría hecho evidente el conflicto — que es
precisamente el argumento de [ADR-006](ADR-006-dominio-determinista.md).

### Tensión 1 — R1 (+10 % máximo) contra R3 (descarga del ~30 %)

Tras recortar un 30 %, volver al volumen anterior exige un salto del **+43 %**, prohibido
por R1. Y si la vuelta se limita al +10 %, el plan **encoge**: en un bloque de cuatro
semanas queda `1,10³ × 0,70 = 0,93`. Un plan de entrenamiento que decrece semana a semana
no es un plan de entrenamiento.

### Tensión 2 — R8 (tirada larga ≤ 35 %) contra las semanas de 3 días

R8 asume semanas de 5–6 días. Con solo tres sesiones, tres bloques de ≤ 35 % obligan a que
las tres sean casi idénticas: no hay tirada larga, hay tres rodajes iguales. En los planes
reales, quien corre 3 días tiene una tirada larga **proporcionalmente más larga**.

### Tensión 3 — R8 contra la tabla de tiradas largas de §3.1

La tabla pide una tirada larga final de 30–32 km para maratón. Con el techo del 35 %, eso
exige semanas de más de 90 km, fuera del alcance de casi cualquier aficionado. Además, si
el volumen sube pero la tirada larga topa en su máximo, el sobrante se acumula en un
rodaje "fácil" **más largo que la propia tirada larga** — una semana absurda que la primera
implementación generaba de verdad.

## Decisión

1. **La descarga recorta un 20 %, no un 30 %.** Es el recorte más profundo que permite que
   el plan siga progresando bajo R1 (`1,10³ × 0,80 = 1,06` por bloque). R1 gana porque es
   la regla que previene lesiones; R3 conserva su función de asimilación.
2. **El techo por sesión es del 35 % con 4 días o más, y del 45 % con 3.** Con 3 días la
   tirada larga se lleva el 42 % del volumen. Se documenta como excepción explícita, no
   como relajación silenciosa.
3. **El volumen semanal se limita a lo que los días disponibles pueden repartir**:
   `tirada_larga_máxima / fracción_de_la_tirada_larga`. Al llegar ahí el plan deja de
   crecer. Antes que emitir una semana con un rodaje fácil de 33 km, el plan se estanca.
4. **La progresión trunca a décimas de kilómetro antes de calcular la semana siguiente.**
   Arrastrar el valor exacto y redondear al final hacía que una semana superara el +10 %
   real respecto a la anterior *ya redondeada*: la regla se cumplía sobre el papel y no
   sobre el plan que recibe el runner.

## Alternativas consideradas

**Aplicar R1 solo a la progresión de carga, excluyendo el rebote posterior a la descarga.**
Es lo que hacen los entrenadores de verdad, y permitiría mantener el 30 %. Descartada
porque el test de [§5](../contexto/02-DOMINIO-RUNNING.md) exige la comprobación entre
*todas* las semanas consecutivas, y relajar el test para salvar la regla sería invertir el
orden correcto de las cosas.

**Exigir un mínimo de 4 días para generar plan.** Resolvería la tensión 2 de raíz, pero
niega el servicio a quien solo puede correr 3 días — que es justamente el perfil que más
necesita orientación.

**Dejar que el LLM ajuste los números cuando las reglas chocan.** Descartada de plano: es
exactamente lo que [ADR-006](ADR-006-dominio-determinista.md) prohíbe. Un conflicto entre
reglas es una decisión de ingeniería, y se resuelve una vez, en código y por escrito.

## Consecuencias

### Positivas

- Las ocho reglas se cumplen **a la vez y de forma verificable**: hay tests que recorren
  las cuatro distancias × tres niveles × cuatro frecuencias de entrenamiento.
- Cada desviación respecto a la documentación queda escrita y justificada, en vez de
  esconderse en una constante mágica.
- El límite del punto 3 hace que el sistema diga implícitamente algo cierto: *no se puede
  preparar un maratón de alto volumen corriendo tres días a la semana*.

### Negativas

- **El dominio ya no coincide literalmente con la documentación** de 02-DOMINIO-RUNNING
  (descarga del 20 % y no del 30 %, techo del 45 % con 3 días). Quien lea solo el
  documento y luego el código encontrará una diferencia; de ahí este ADR.
- **La progresión es conservadora.** Con ~6 % de crecimiento por bloque de cuatro semanas,
  el volumen inicial pesa más que el pico teórico: un plan de 12 semanas apenas crece un
  20 % sobre su punto de partida. Es seguro, pero un entrenador humano probablemente
  progresaría más rápido con un corredor experimentado.
- **La tirada larga de maratón se queda en ~25–32 km** en vez de los 30–32 km de la tabla,
  salvo en volúmenes muy altos. Para un maratón esto importa: la tirada larga es la sesión
  que más se parece a la carrera.
- Los topes por frecuencia son **valores elegidos con criterio, no derivados de un estudio
  concreto**. Están aislados en constantes con nombre para poder discutirlos, pero no
  dejan de ser un juicio.

# ADR-014 · Los avisos programados viven en memoria, no en un jobstore

**Estado:** Aceptado
**Fecha:** 2026-08-14

## Contexto

[00-CONTEXTO](../contexto/00-CONTEXTO.md) y [07-PLAN-EJECUCIÓN](../contexto/07-PLAN-EJECUCION.md)
fijaban "APScheduler con jobstore en PostgreSQL" para los recordatorios. Al implementarlo
aparecieron dos cosas que el plan no había previsto.

**La primera es de diseño.** El proyecto ya tiene una tabla `recordatorios` — la pide el
modelo de datos de [02 §4](../contexto/02-DOMINIO-RUNNING.md) — con el runner, el tipo y
la hora local. Un jobstore en Postgres guardaría *ese mismo horario otra vez*, en su propio
formato. Dos copias del mismo dato que se escriben por caminos distintos acaban
divergiendo: el runner cambia su hora, uno de los dos escritos falla, y el correo sigue
llegando cuando ya no toca. El síntoma aparecería días después y sin rastro en los logs.

**La segunda es de dependencias.** APScheduler 3 no habla con drivers asíncronos, así que
un jobstore en Postgres obliga a instalar un segundo driver (`psycopg2`) solo para él,
conviviendo con el `asyncpg` de la app. Una dependencia más, una URL más que mantener en
sincronía y un modo de fallo más.

## Decisión

**Los jobs viven en memoria, y al arrancar se reconstruyen leyendo la tabla
`recordatorios`.** Esa tabla es la única fuente de verdad del horario; APScheduler queda
reducido a lo que sabe hacer bien: calcular cuándo toca el próximo disparo en la zona
horaria del runner y despertarse.

Cada job lleva **solo un `runner_id` y un tipo** como argumentos. Los datos del runner se
vuelven a cargar acotados por ese id cuando toca enviar, según
[03 §4.5](../contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md).

## Alternativas consideradas

**El jobstore en Postgres del plan original.** Aguanta un reinicio sin releer nada y es lo
que estaba escrito. Descartado por la duplicación de estado: el problema que resuelve
(sobrevivir al reinicio) ya lo resuelve la reconstrucción al arrancar, y a cambio no
introduce una segunda copia del horario.

**Un único job que cada cinco minutos pregunte "¿a quién le toca ahora?"**. Menos código y
sin reconstrucción. Descartado por el punto de seguridad de §4.5: ese job es exactamente la
consulta que barre a todos los usuarios y reparte correos, que es donde se cuela un cruce
de destinatarios. Un job por runner hace que el aislamiento sea estructural y no una
condición que haya que recordar escribir bien.

## Consecuencias

### Positivas

- **Una sola fuente de verdad** para cuándo se escribe a cada runner.
- Una dependencia menos (`psycopg2`) y una URL de base de datos menos que mantener.
- La reconstrucción al arrancar es **autocurativa**: si un job se perdiera por lo que
  fuese, el siguiente despliegue lo restaura desde la tabla.
- El aislamiento entre usuarios sigue siendo estructural: el job no puede tocar datos de
  otro porque no los tiene.

### Negativas

- **Entre el arranque y la reconstrucción no hay avisos programados.** Es una ventana de
  milisegundos, pero existe: un aviso que cayera justo ahí se perdería. `misfire_grace_time`
  de una hora lo cubre en la práctica, no en teoría.
- **Con más de un proceso, cada uno programa los mismos avisos y el runner recibe copias.**
  Hoy no es un problema porque se despliega un solo proceso, pero es una bomba de relojería
  para el día que se escale horizontalmente: haría falta un cerrojo distribuido o mover
  esto a EventBridge, que es lo que ya figura en el Roadmap del README.
- **El arranque hace una consulta que cruza usuarios** (`activos_de_todos`). Es la única del
  proyecto y está acotada a devolver la agenda — a quién y a qué hora —, nunca datos
  personales. Aun así es una excepción a la regla, y las excepciones se documentan.
- **Se aparta de lo que dice la documentación de contexto**, que sigue diciendo "jobstore en
  PostgreSQL". Quien lea el documento y luego el código encontrará una diferencia; de ahí
  este ADR.

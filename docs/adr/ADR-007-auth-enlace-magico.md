# ADR-007 · Autenticación por enlace mágico, sin contraseñas

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

El diseño inicial (v1 y v2) no contemplaba usuarios: había una sola conversación y una sola memoria. Al revisarlo se detectó un fallo grave: **la memoria a largo plazo sería global**. Los hechos de un runner (*"le duele la rodilla derecha"*) se inyectarían en el contexto de cualquier otro.

Eso es una fuga de datos personales, una corrupción del producto y —lo peor— un **fallo silencioso**: no lanza excepción, no aparece en los logs, y la aplicación parece funcionar correctamente.

Hacía falta identidad de usuario. Con 4 días de plazo y un mecanismo de correo ya necesario para los recordatorios.

## Decisión

**Autenticación por enlace mágico (passwordless).** El usuario introduce su correo, recibe un enlace de un solo uso válido 15 minutos, y al abrirlo obtiene una sesión JWT en una cookie `httpOnly` + `Secure` + `SameSite=Lax`.

El `runner_id` es la **frontera de aislamiento** y se aplica en cinco capas: firmas de repositorio, identidad desde el JWT, punto único de ensamblado de contexto, URLs firmadas para archivos, y jobs del scheduler acotados por runner. Verificado con una carpeta `tests/security/`.

## Alternativas consideradas

**Correo + contraseña.** Descartado: obliga a almacenar y hashear contraseñas, gestionar recuperación, y **no verifica el correo** — que se necesita verificado de todas formas para poder mandar recordatorios sin arruinar la reputación de envío. Más trabajo y más superficie de ataque para menos garantías.

**Amazon Cognito.** Sería "la forma AWS" y encajaría con [ADR-004](ADR-004-aws-servicios-gestionados.md). Descartado por tiempo: user pools, hosted UI, flujo OAuth y verificación de JWKS suman fácilmente una jornada de las cuatro disponibles, y añaden una dependencia difícil de simular en los tests.

**OAuth con Google.** Buena experiencia de usuario, pero exige configurar una pantalla de consentimiento y un dominio verificado, y no da el correo verificado para envíos de forma tan directa. Descartado por trámites.

**Identificador anónimo en el navegador** (sin login). Descartado: no sobrevive a cambiar de dispositivo ni a limpiar el navegador, y no da una dirección de correo — con lo que **los recordatorios, que son un punto extra del enunciado, serían imposibles**.

## Consecuencias

### Positivas

- **Un solo componente resuelve tres problemas:** identidad, verificación de correo y canal de notificaciones. SES ya estaba en el plan.
- **No se almacenan contraseñas** → desaparece toda una familia de vulnerabilidades.
- **Elimina el fallo silencioso** que motivó este ADR, de forma estructural: la firma de los repositorios hace que el bug no se pueda escribir.
- Los tests de aislamiento son un artefacto concreto que enseñar en una revisión de código.

### Negativas

- **Depende del correo.** Si SES falla o el mensaje cae en spam, el usuario **no puede entrar**. Es un punto único de fallo para el acceso. Se mitiga verificando los remitentes y probando la entrega antes de la demo.
- **Fricción en cada inicio de sesión** — hay que salir de la app, abrir el correo y volver. Se compensa con una sesión larga (30 días).
- **SES en sandbox solo envía a direcciones verificadas**, lo que en la práctica limita quién puede probar la demo hasta obtener acceso de producción.
- Añade trabajo (~3 h) a un plazo ya ajustado, y desplaza otras features hacia el final de la lista de prioridades.

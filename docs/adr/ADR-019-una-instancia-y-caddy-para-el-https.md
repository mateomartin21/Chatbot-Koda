# ADR-019 · Una instancia EC2 con Caddy, y el HTTPS sin comprar dominio

**Estado:** Aceptado
**Fecha:** 2026-08-15

## Contexto

Koda está terminada y no se puede enseñar. El motivo no es de producto: es que
**`getUserMedia` solo existe en un origen seguro**. Sin HTTPS no hay micrófono en el
móvil, y sin micrófono no hay nada que grabar — la voz es la mitad del proyecto. El
despliegue no es el último paso de la lista, es lo que bloquea el vídeo de demo.

Dos restricciones acotan la decisión y no son negociables a estas alturas:

**El proyecto necesita WebSockets.** Nova Sonic ([ADR-011](ADR-011-nova-sonic-y-gateway-de-modelos.md))
habla por `/ws/voz` con streaming bidireccional. Eso descarta de golpe todo lo que
sirva peticiones HTTP sueltas: Lambda con Function URL no hace WebSocket, y App Runner
tampoco. La opción más cómoda de AWS no sirve para este proyecto en concreto.

**No hay dominio.** Let's Encrypt no firma certificados para direcciones IP, y ACM solo
emite si controlas el DNS de un dominio. Comprar uno son 12 € y un rato de propagación
por algo que se tira en una semana.

Y hay un detalle heredado que condiciona todo lo demás: el SDK de Nova Sonic
(`aws_sdk_bedrock_runtime`) resuelve credenciales **solo** por variables de entorno.
No mira el metadata de la instancia. Un rol de IAM — la respuesta correcta a "no metas
llaves en un servidor" — deja la voz en tiempo real sin credenciales.

## Decisión

### 1. Una instancia EC2 con tres contenedores

`t3.small` con Ubuntu 24.04 y `docker compose`: PostgreSQL, la aplicación y Caddy
delante. Un `git pull && docker compose up -d --build` despliega.

### 2. Caddy pone el HTTPS, y no se administra

Caddy pide el certificado a Let's Encrypt al arrancar y lo renueva solo. El HTTPS de
este proyecto no es un script de cron ni una tarea pendiente: es el comportamiento por
defecto del proxy. Y `reverse_proxy` pasa el `Upgrade` de WebSocket sin configuración,
que es justo lo que hacía falta.

### 3. El nombre sale de la IP: `sslip.io`

`54-91-20-3.sslip.io` resuelve a `54.91.20.3` por un DNS público. Es un nombre de
verdad, así que Let's Encrypt lo firma. Cero coste, cero espera de propagación.

Obliga a una **IP elástica**: si la IP cambia, el nombre deja de apuntar al servidor,
el certificado deja de valer y los enlaces mágicos ya enviados dejan de funcionar.

### 4. PostgreSQL en el mismo servidor, no RDS

[07-PLAN-EJECUCION](../contexto/07-PLAN-EJECUCION.md) decía "PostgreSQL gestionado".
Se cambia. RDS son un grupo de subredes, un grupo de seguridad, ocho minutos de
aprovisionamiento y una segunda cosa que puede fallar el día del despliegue, para una
base de datos que en toda su vida va a tener los datos de las personas que evalúen
esto. `DATABASE_URL` es una sola variable de entorno: mover Koda a RDS es cambiar esa
línea, y por eso posponerlo no cuesta nada más adelante.

### 5. Las credenciales van en un `.env` del servidor, con `chmod 600`

No en la imagen — el `.dockerignore` excluye el `.env` a propósito, porque una imagen
se comparte y sus capas conservan lo que se horneó dentro. Y no en un rol de IAM,
porque Nova Sonic no lo leería.

### 6. Las migraciones corren en un contenedor aparte

`alembic upgrade head` es un servicio que corre y termina; la aplicación depende de
que haya terminado bien. Si una migración falla, la aplicación no arranca. Un fallo de
despliegue tiene que verse como un fallo de despliegue y no como una aplicación viva
que contesta 500 a todo.

### 7. Un solo worker de uvicorn

APScheduler agenda los recordatorios **en memoria** ([ADR-014](ADR-014-jobs-en-memoria.md)).
Con dos workers, cada uno reconstruye la misma agenda al arrancar y cada correo sale
por duplicado.

## Alternativas consideradas

**AWS App Runner.** Es lo que uno elegiría: contenedor, HTTPS con dominio propio
incluido, escalado solo. **No soporta WebSocket**, así que Nova Sonic no funciona.
Habría que desplegar sabiendo que la mejor función del proyecto está apagada.

**Lambda + Function URL.** Más barato todavía y con HTTPS gratis. Mismo muro: sin
WebSocket. Además APScheduler no tiene dónde vivir entre invocaciones.

**ECS Fargate + ALB.** Funciona y es lo correcto con tráfico real. El ALB necesita un
certificado de ACM, ACM necesita un dominio, y volvemos a comprar dominio — con la
tarea añadida de mantener un cluster para un contenedor. Más piezas que problema.

**Comprar un dominio y usar ACM o Let's Encrypt normal.** Es lo que haría un producto
de verdad, y el enlace no daría vergüenza. Se descarta por tiempo: quedan dos días y
la propagación de DNS puede comerse una tarde justo cuando no sobra ninguna.

**Un certificado autofirmado.** Gratis e inmediato. Inútil: el navegador del móvil
muestra una pantalla roja de advertencia, y aunque la aceptes, quien vea el vídeo verá
esa pantalla. La primera impresión sería que el proyecto está roto.

**Túnel de Cloudflare o ngrok.** HTTPS instantáneo sin tocar nada. Se descarta porque
el enlace se cae cuando se cierra el proceso, y lo que hace falta es una dirección que
siga viva cuando alguien abra la entrega tres días después.

## Consecuencias

### Positivas

- El micrófono funciona en el móvil. Sin esto no hay vídeo, y sin vídeo la mayoría de
  quienes evalúan no ven nada.
- WebSocket funciona, así que la voz en tiempo real se enseña de verdad y no como una
  captura de pantalla.
- El certificado se renueva solo. No hay nada que recordar hacer.
- Levantar Koda en otro servidor son tres pasos: clonar, escribir el `.env`, `docker
  compose up`.
- La base de datos no está publicada en internet ni un segundo: no expone puertos y
  solo se alcanza desde la red interna de Docker.
- El mismo `Dockerfile` corre en CI, así que un despliegue roto se ve en el push y no
  al desplegar.

### Negativas

- **La dirección es fea y depende de un tercero.** `54-91-20-3.sslip.io` no inspira
  confianza en una entrega, y si sslip.io cayera, el certificado no se podría renovar.
- **Un solo servidor es un solo punto de fallo.** Si la instancia se cae, Koda está
  caída. No hay réplica, ni balanceador, ni salud vigilada por nadie.
- **Las credenciales de AWS están en un fichero del servidor.** Con `chmod 600` y sin
  salir de ahí, pero cualquiera que entre por SSH las tiene. La alternativa correcta
  —un rol de IAM— rompe la voz, así que se elige a sabiendas y no por descuido.
- **Los datos viven en un volumen de Docker de esa máquina.** Sin copias de seguridad,
  sin réplicas y sin recuperación a un punto en el tiempo. `docker compose down -v`
  escrito de más los borra todos.
- **Se incumple el plan de ejecución**, que pedía PostgreSQL gestionado. Es una
  decisión de plazo, y la deuda queda anotada aquí en vez de disimulada.
- **Un solo worker es un solo proceso.** Con concurrencia de verdad se notaría; el
  saneado de fotos con Pillow, que no es asíncrono ([ADR-017](ADR-017-la-foto-se-reprocesa-antes-de-salir.md)),
  bloquearía a todo el mundo y no solo a quien mandó la foto.
- **La instancia gasta crédito mientras esté encendida**, y una IP elástica sin
  instancia asociada se cobra igual. Apagar tiene que ser un paso explícito, y por eso
  está escrito al final del runbook.
- **Nada de esto está probado todavía en un móvil real.** Está construido y verificado
  en local con la misma imagen que va a correr en el servidor, pero el micrófono en un
  iPhone sigue siendo una promesa hasta que se pruebe.

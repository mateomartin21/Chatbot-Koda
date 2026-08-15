# ADR-022 · El correo tiene que llegarle a alguien que no conozco

**Estado:** Aceptado
**Fecha:** 2026-08-15

## Contexto

[ADR-010](ADR-010-sin-dominio-propio-para-ses.md) decidió no comprar dominio y aceptar
el riesgo de spam. Lo que no midió es la otra consecuencia, que es mucho peor:

**Amazon SES arranca en modo sandbox, y en sandbox solo entrega a direcciones que
hayas verificado tú a mano.**

Para casi cualquier aplicación eso sería una molestia. Para Koda es la puerta cerrada:
la única forma de entrar es un enlace mágico por correo
([ADR-007](ADR-007-auth-enlace-magico.md)). Con SES en sandbox, **nadie a quien no
conozcas de antemano puede usar Koda**. No es que no reciba recordatorios: es que no
puede ni entrar.

Y quien va a intentarlo es precisamente alguien cuyo correo no se sabe: la persona que
evalúe esto. Escribirá su dirección en la portada, SES la rechazará por no estar
verificada, y Koda se verá exactamente igual que si estuviera rota.

Hay un segundo problema, más pequeño pero del mismo tipo: **los recordatorios salen a
las 6:00, a las 20:00 y los domingos a las 19:00**, en la hora local del runner. Son
buenas horas para entrenar y horribles para enseñar. Nadie que abra Koda a las once de
la mañana va a esperar hasta mañana para comprobar que los correos funcionan.

## Decisión

### 1. Salir del sandbox es lo primero, y no lo puede hacer el código

Se pide acceso de producción a SES desde la consola. Es gratis, y hasta que AWS lo
apruebe **la aplicación no sirve para nadie más que para su autor**. Es un paso
manual y por eso está escrito al principio del runbook de despliegue, no al final.

### 2. Y como AWS aprueba cuando quiere, hay un segundo camino

`PROVIDER_EMAIL=smtp` levanta `SMTPEmail` en lugar de `SESEmail`. Cuatro variables de
entorno y ni una línea de código: es el mismo `EmailPort` de siempre, que es
exactamente para lo que existía el puerto.

**Se eligió SMTP y no la API de otro proveedor** a propósito. SMTP lo hablan Gmail,
Brevo, SendGrid, Mailgun y el propio SES: un adaptador sirve para todos y cambiar de
proveedor no vuelve a ser un cambio de código. Con la API REST de Resend, en cambio,
habría que escribir un adaptador nuevo por cada proveedor — y además Resend, sin
dominio verificado, **tiene la misma limitación que SES**: solo entrega a tu propia
dirección. Habría sido cambiar un muro por el mismo muro.

Usa la librería estándar dentro de un hilo, como el adaptador de SES hace con boto3.
No merece una dependencia nueva.

El puerto se elige por `SMTP_PORT`: 465 abre TLS desde el primer byte, 587 empieza en
claro y sube con STARTTLS. Mandar por 587 sin `starttls()` entregaría la contraseña en
claro, así que la decisión se toma por puerto y no se deja al azar.

### 3. Un recordatorio se puede pedir ahora

`configurar_recordatorio` acepta `mandar_ahora`. Koda entrega ese correo al momento,
sin tocar la hora ni el estado — es enseñarlo, no reconfigurarlo. Si de paso moviera la
hora, pedir "mándamelo para verlo" a las once de la noche dejaría el aviso diario a las
once de la noche.

Usa **el mismo camino** que el job del scheduler, no una copia. Si el correo de prueba
se redactara aparte, sería posible que el de prueba saliera bien y el de verdad no —
que es el peor de los tres resultados posibles.

### 4. Las horas por defecto se quedan como están

6:00 la sesión del día, 20:00 el check-in, domingo 19:00 el resumen, en la hora local
del runner. Se dan de alta solos al entrar, y son opt-out: un recordatorio que hay que
activar a mano no lo activa casi nadie. Quien quiera otra hora se lo dice a Koda
hablando, que es la forma de configurar que tiene esta aplicación.

## Alternativas consideradas

**Verificar a mano la dirección del evaluador.** Es lo que SES permite hacer sin salir
del sandbox, y es inútil aquí: hay que saber la dirección de antemano, y no se sabe.

**Comprar un dominio y verificarlo en SES.** No resuelve nada: verificar un dominio
permite enviar *desde* él, pero el sandbox limita a *quién* se envía. Son dos cosas
distintas y hay que pedir producción igual.

**Enseñar el enlace mágico en pantalla si el correo falla.** Resolvería la demo en diez
minutos y convertiría la autenticación en un adorno: cualquiera podría entrar como
cualquiera escribiendo su correo. Se descarta sin más.

**Una cuenta de invitado ya creada, con la sesión abierta.** Más honesto que lo
anterior y aun así malo: el momento que mejor demuestra Koda es *volver a entrar y que
se acuerde de ti*, y con una cuenta compartida ese momento no existe — la memoria sería
la de todos los evaluadores mezclada, que además es justo lo que ADR-021 y la suite de
aislamiento se dedican a impedir.

**Quedarse solo con SMTP y jubilar SES.** Tentador por simplicidad. Se descarta porque
SES es el proveedor elegido en [ADR-004](ADR-004-aws-servicios-gestionados.md) y
funciona; el problema no es SES, es el sandbox, y eso se arregla con una solicitud.
SMTP es el seguro, no el sustituto.

**Bajar las horas de los recordatorios para que se puedan enseñar.** Sería estropear el
producto para facilitar la demo. Las 6:00 son la hora correcta para avisar de un
entrenamiento; lo que hacía falta era poder pedir uno fuera de hora.

## Consecuencias

### Positivas

- Con el sandbox resuelto —por producción o por SMTP— cualquiera puede entrar en Koda,
  que es el requisito mínimo para que exista como producto.
- El puerto `EmailPort` demuestra que servía para algo: cambiar de proveedor de correo
  es una variable de entorno.
- Un adaptador SMTP vale para Gmail hoy y para cualquier proveedor mañana.
- Los recordatorios se pueden demostrar en diez segundos, y con el correo de verdad,
  no con uno de mentira escrito para la ocasión.
- El arranque avisa si falta la configuración del proveedor elegido, así que un
  despliegue a medias se ve al arrancar.

### Negativas

- **Salir del sandbox depende de AWS y no de este proyecto.** Puede tardar horas o
  días, y puede denegarse. Por eso hay plan B, pero el plan B tiene lo suyo.
- **Gmail por SMTP exige una contraseña de aplicación**, y para eso hay que tener la
  verificación en dos pasos activada en la cuenta. Es una credencial más en el `.env`
  del servidor, con el mismo problema que ya documenta
  [ADR-019](ADR-019-una-instancia-y-caddy-para-el-https.md).
- **Un correo enviado desde Gmail tiene bastantes papeletas de caer en spam** cuando va
  a un dominio corporativo, que es justo donde va a ir. El riesgo que ADR-010 aceptó se
  agrava, no se arregla.
- **Gmail limita a unos 500 envíos al día** y reescribe el remitente al de la cuenta,
  así que `SMTP_FROM` puede quedarse en decoración.
- **`SMTPEmail` no tiene test contra un servidor de verdad.** Se prueba que arma bien
  el mensaje; que Gmail lo acepte es una promesa hasta que se mande uno.
- **`mandar_ahora` permite que alguien se autoenvíe correos en bucle** pidiéndoselo a
  Koda. No hay límite de frecuencia. Con un usuario da igual; es una puerta abierta que
  queda anotada.
- **Dos proveedores de correo posibles significa dos caminos que mantener**, y solo uno
  se usa a la vez — así que el otro se pudre sin que nadie lo note.

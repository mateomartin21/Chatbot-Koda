# ADR-024 · El enlace mágico vale durante su ventana, no una sola vez

**Estado:** Aceptado
**Fecha:** 2026-08-16
**Supersede parcialmente:** [ADR-007](ADR-007-auth-enlace-magico.md), solo en lo del uso único

## Contexto

[ADR-007](ADR-007-auth-enlace-magico.md) decidió autenticar con un enlace mágico **de un
solo uso** válido 15 minutos. Y [03-MULTIUSUARIO-Y-SEGURIDAD.md](../contexto/03-MULTIUSUARIO-Y-SEGURIDAD.md)
justificaba el uso único con esta frase:

> Un enlace reenviado o cacheado por un antivirus de correo no vale dos veces.

Esa frase describe bien la intención y **describe mal la consecuencia**. Si un antivirus
de correo abre el enlace, el que se queda sin usarlo no es el atacante: es el
destinatario. Los sistemas de correo corporativo —Microsoft Defender con Safe Links,
casi cualquier pasarela antimalware— **visitan los enlaces para analizarlos antes de
entregar el mensaje**. Cuando llegan a un token de un solo uso, se llevan el único uso.
La persona hace clic y se encuentra un enlace muerto.

Cuando el enlace mágico es la **única** forma de entrar, eso no es una molestia: es no
poder entrar, y desde fuera se ve exactamente igual que una aplicación rota.

Salió probando en un iPhone: en Mail basta rozar el enlace para que se abra, y con eso
ya estaba gastado. Pero el iPhone solo fue el mensajero. El caso que importa es el
evaluador con una dirección corporativa, que es justo quien más papeletas tiene de estar
detrás de una pasarela que preanaliza enlaces.

## Decisión

El token deja de ser de un solo uso. Vale mientras **no haya caducado**, y admite varios
canjes dentro de esos 15 minutos.

```python
def esta_vigente(self, ahora: datetime) -> bool:
    return ahora < self.expira_en          # antes: usado_en is None and ...
```

`usado_en` se sigue guardando, y se escribe **solo en el primer canje**: pasa de ser un
dato que decide a un dato que se consulta. Saber cuándo se estrenó un enlace sirve para
investigar; sobrescribirlo en cada canje lo convertiría en "la última vez", que no es lo
que dice el nombre.

El test de seguridad que fijaba el uso único ahora fija lo contrario, con el porqué
escrito encima. Y se añade uno nuevo: que canjearlo **no prorroga** la caducidad, porque
al quedar la expiración como única barrera, más vale que esa barrera cierre.

## Alternativas consideradas

**Dejarlo como estaba.** Es la postura más segura sobre el papel y la que falla en el
sitio equivocado: protege contra un enlace filtrado a costa de dejar fuera a un usuario
legítimo cuyo correo pasa por un antivirus. Se descarta porque el modo de fallo es peor
que el ataque del que protege.

**Un código de seis dígitos en el correo,** que se teclea en la aplicación. Es la
solución bonita: no depende de abrir enlaces, funciona igual en una app instalada y en un
navegador, y no le importa lo que haga el antivirus. Se descarta **por tiempo**, no por
diseño: introduce un segundo tipo de secreto con su propia superficie de fuerza bruta —
seis dígitos son un millón de combinaciones y hacen falta límites de intentos— y esto se
decidió la víspera de la entrega. Es lo primero que haría después.

**Distinguir al antivirus del usuario** por User-Agent o por si la petición no lleva
cabeceras de navegador. Frágil, se equivoca en los dos sentidos, y convierte una regla de
seguridad en una heurística que hay que mantener.

**Bajar la caducidad a 5 minutos** para compensar. Suena a contrapartida razonable y en
la práctica añade un fallo nuevo: alguien que lee el correo diez minutos después, que es
de lo más normal, se queda fuera.

## Consecuencias

### Positivas

- Un antivirus de correo ya no puede dejar a nadie fuera. Es el motivo entero.
- Reintentar funciona: abrir el enlace, que falle la conexión y volver a tocarlo ya no
  condena a pedir otro.
- En iOS, la aplicación instalada puede canjear un enlace que ya se abrió en el
  navegador, que es lo que hace usable el acceso desde la pantalla de inicio
  ([ADR-023](ADR-023-moderar-las-fotos-y-poder-limpiar-el-chat.md) trajo el campo para
  pegarlo; sin este ADR, ese campo casi nunca funcionaba).
- La caducidad queda como una única regla, fácil de razonar y de probar.

### Negativas

- **Un enlace filtrado o reenviado funciona varias veces durante 15 minutos**, no una.
  Quien consiga el correo en esa ventana entra tantas veces como quiera. Es el precio, y
  es real.
- **Se debilita una propiedad que estaba escrita, probada y defendida** en ADR-007. Una
  decisión anterior se revierte con menos de un día de plazo, sin haber visto el problema
  en producción con un evaluador real: se actúa sobre un riesgo razonado, no medido.
- **El correo sigue siendo el único factor.** Este ADR no toca eso, y ahora ese único
  factor aguanta un poco menos.
- **Un token robado ya no se "quema" al usarse**, así que el usuario legítimo entrando no
  invalida la copia del atacante, como pasaba antes por accidente.
- **La mitigación de verdad es el código de seis dígitos** y sigue sin estar. Esto es un
  parche razonado, no el destino.

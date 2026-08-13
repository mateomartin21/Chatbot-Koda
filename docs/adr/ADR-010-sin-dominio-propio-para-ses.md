# ADR-010 · Sin dominio propio para SES — se acepta el riesgo de spam

**Estado:** Aceptado
**Fecha:** 2026-08-14

## Contexto

`SES_FROM_EMAIL` es actualmente `kodacoach@gmail.com`, una dirección de Gmail verificada
individualmente en SES (no un dominio propio). Para el destinatario (Gmail), un correo que
dice venir de `@gmail.com` pero se envía desde servidores de AWS SES —no desde la
infraestructura real de Google— es indistinguible de un intento de suplantación, así que
sus filtros lo marcan como spam con frecuencia.

La solución correcta es verificar un **dominio propio** en SES con Easy DKIM (y opcionalmente
un dominio de MAIL FROM personalizado), lo que permite alinear SPF/DKIM y demostrarle a
Gmail que el correo es legítimo.

Se intentó comprar `kodarunning.com` con los $100 de crédito promocional de AWS vía Route 53,
pero la API rechazó la operación: `AccessDeniedException: Free Tier accounts are not
supported for this service`. Es una restricción de la cuenta, no de configuración — las
cuentas con crédito promocional no pueden registrar dominios en Route 53. El crédito sigue
sirviendo para Bedrock, Polly, Transcribe y SES; no para esto.

## Decisión

**No comprar un dominio para este proyecto.** Se mantiene `kodacoach@gmail.com` como
remitente verificado individualmente, aceptando que los correos (enlaces mágicos,
recordatorios) pueden caer en la carpeta de spam del destinatario.

## Alternativas consideradas

**Comprar el dominio en otro registrador** (Namecheap, Cloudflare, GoDaddy) pagando con
dinero real, ~$10-15/año, y verificar DKIM manualmente en SES. Descartado por ahora: es un
gasto y un trámite adicional (compra, DNS, propagación, verificación) que no aporta a la
tesis del proyecto ni a los puntos evaluados, con un plazo de cuatro días ya ajustado.

**Solicitar salida del sandbox de SES sin dominio propio.** No resuelve el problema de fondo
— la reputación de envío y la alineación SPF/DKIM son independientes del sandbox, y sin
dominio propio Gmail seguiría viendo el remitente como no alineado.

## Consecuencias

### Positivas

- Cero gasto adicional y cero trabajo extra en un plazo ya ajustado.
- El riesgo es conocido, está documentado, y tiene una solución clara si en el futuro se
  justifica el gasto (comprar dominio + verificar DKIM en SES).

### Negativas

- **Los correos de Koda (enlace mágico, recordatorios) pueden llegar a spam**, incluido
  potencialmente el del evaluador. Hay que avisarlo explícitamente en la entrega y en el
  vídeo de demo — revisar spam si el correo "no llega".
- Es una limitación visible en un flujo central del producto (la autenticación depende del
  correo — ver [ADR-007](ADR-007-auth-enlace-magico.md)), no un detalle menor.
- Si el proyecto continuara más allá de la entrega, este es el primer punto de deuda técnica
  a resolver antes de tener usuarios reales.

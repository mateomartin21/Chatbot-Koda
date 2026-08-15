# ADR-017 · La foto se reprocesa antes de salir del servidor

**Estado:** Aceptado
**Fecha:** 2026-08-14

## Contexto

[ADR-008](ADR-008-entradas-multimodales.md) dejó decidido que habría entrada por
foto y que el caso de uso estrella era **leer la pantalla del reloj**. Faltaba
construirlo, y al hacerlo aparecen tres decisiones que no son obvias.

**La primera es de privacidad, y es la que importa.** Una foto sacada con un móvil
lleva EXIF, y el EXIF lleva las **coordenadas GPS del sitio donde se sacó**. El
gesto que esta función invita a hacer es fotografiar el reloj justo al terminar de
correr: en la puerta de casa, o en el parque de al lado. Reenviar ese archivo tal
cual a Bedrock sería mandarle a un tercero dónde vive alguien que solo quería
apuntar sus kilómetros. Nadie lo pidió y nadie se enteraría.

**La segunda es de honestidad del sistema.** El gateway de modelos
([ADR-011](ADR-011-nova-sonic-y-gateway-de-modelos.md)) encadena varios proveedores,
y no todos ven: el tier de Groq es un modelo de texto. Si le llega una foto, no
recibe la imagen pero **sí recibe el texto que la acompaña** — "registra esto" — y
contesta encantado como si la hubiera mirado. El runner se queda creyendo que su
entrenamiento quedó apuntado. Es el peor fallo posible de esta función porque es
silencioso.

**La tercera es de confianza en el dato.** Los números salen de un modelo leyendo
una pantalla pequeña en una foto movida. Se equivoca.

## Decisión

### 1. Toda foto se reprocesa en el borde, antes de tocar nada más

`app/infrastructure/imagenes/sanitizar.py` abre los píxeles con Pillow y vuelve a
codificar a JPEG. Lo que no son píxeles no sobrevive: EXIF, GPS, marca del teléfono
y miniatura incrustada se quedan fuera porque **no se copian**, no porque se borren.

Resuelve tres cosas de un golpe:

| | |
|---|---|
| **Metadatos** | Lo que no se pasa a `save()`, no viaja |
| **Archivos con sorpresa** | Lo que entra se decodifica de verdad; lo que no sea una imagen válida revienta aquí, dentro de un `try`, y no más adelante |
| **Coste y latencia** | 12 MP y varios MB pasan a 1600 px de lado. Para leer los números de un reloj sobra |

Se hace en `POST /api/mensajes`, **antes** de llamar al modelo: una foto que no se
puede abrir se contesta sin gastar una sola llamada.

La orientación se aplica **antes** de tirar el EXIF (`exif_transpose`). Sin ese
detalle, una foto vertical llega girada y el modelo intenta leer un reloj tumbado.

### 2. El puerto solo acepta imágenes ya saneadas

`Imagen` es un tipo del dominio (`app/domain/ports/llm_port.py`) y solo lo produce
el saneador. Un adaptador no puede mandar por error los bytes que subió el
navegador, porque no tiene forma de construir una `Imagen` con ellos.

### 3. Un modelo que no ve, no contesta

`LLMPort` gana `soporta_imagenes`, igual que ya tenía `soporta_herramientas`. Con
foto, el gateway **solo prueba los tiers que ven**. Si ninguno está disponible, se
dice — "ahora mismo no puedo mirar fotos, dime los kilómetros y lo apunto igual" —
en lugar de dejar que un modelo ciego improvise. Antes ninguna respuesta que una
inventada.

### 4. Lo leído de una foto marca la sesión, pero no recalcula nada

La herramienta `registrar_entrenamiento` da la sesión por hecha y guarda lo corrido
como un hecho de memoria. **No toca la marca del runner**, que es de donde salen
todos sus ritmos. Esos siguen calculándose solo con una marca que él haya
confirmado a mano.

Y el prompt obliga a **repetirle los números al runner**: es su única forma de
darse cuenta de que el modelo leyó mal.

## Alternativas consideradas

**Mandar la foto tal cual y confiar en que Bedrock ignore el EXIF.** Probablemente
lo ignore. Pero "probablemente" no es una política de privacidad, y el archivo ya
habría salido de nuestro servidor con las coordenadas dentro.

**Quitar el EXIF sin recodificar** (`piexif` y similares). Más rápido y conserva la
calidad original, pero solo resuelve el primero de los tres problemas: ni valida que
sea una imagen, ni reduce el tamaño. Recodificar los resuelve todos con menos código.

**Guardar la foto y mandar una URL firmada.** Es lo que insinuaba ADR-008 y lo que
haría falta para que el runner pueda volver a verla. Se descarta por alcance: exige
almacenamiento, caducidad y comprobación de propiedad, y la foto solo hace falta
durante el turno en el que se manda.

**Dejar que el modelo actualice la marca del runner desde la foto.** Es tentador —
"veo un 10K en 43:20, ya tengo su marca" — y es exactamente donde el LLM dejaría de
ser la interfaz para pasar a ser la fuente de verdad, que es lo que
[ADR-006](ADR-006-dominio-determinista.md) prohíbe. Un dígito mal leído cambiaría
todos sus ritmos y ninguno de los dos se enteraría.

## Consecuencias

### Positivas

- Ninguna coordenada GPS sale del servidor, y hay un test que lo comprueba con una
  foto que sí las lleva.
- Un archivo que no sea una imagen se rechaza sin gastar una llamada al modelo.
- El sistema no puede fingir que vio una foto: o la ve, o lo dice.
- Registrar un entrenamiento por foto mueve la próxima sesión del plan, así que Koda
  deja de decir "hoy te toca" justo después de que le cuenten que ya salieron.
- Una dependencia nueva (Pillow) que además hará falta para el vídeo del roadmap.

### Negativas

- **Recodificar pierde calidad.** Un JPEG a 82 sobre una pantalla de reloj con poca
  luz puede volverse ilegible justo en los dígitos que importan. No se ha medido con
  fotos reales de relojes: se ha elegido el valor por criterio, no por prueba.
- **Reprocesar cuesta CPU en el hilo del servidor.** Pillow no es asíncrono y esto
  no se sacó a un hilo aparte: una foto grande bloquea el bucle de eventos unos
  cientos de milisegundos. Con un usuario no se nota; con cien, sí.
- **La foto no se guarda.** El runner no puede volver a verla ni corregir lo que se
  registró a partir de ella; solo puede decírselo a Koda por voz o por texto.
- **Los formatos de Apple (HEIC) dependen de que Pillow tenga el plugin.** Están en
  la lista de aceptados, pero sin `pillow-heif` instalado un iPhone que no convierta
  a JPEG al subir se va a encontrar con "esa foto no la puedo abrir". No se ha
  probado en un iPhone real.
- **Todo esto vale para una foto por turno.** No hay soporte para mandar varias, y
  el esquema tampoco lo insinúa.
- **La lectura del reloj no se ha probado contra fotos de verdad.** Está construida
  y testeada con dobles; que un modelo lea bien un Garmin a contraluz es una promesa
  sin verificar hasta que se pruebe en el móvil.

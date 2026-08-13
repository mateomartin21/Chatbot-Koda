# 04 · Entradas multimodales

> El usuario no siempre puede hablar. Está en la oficina, en el metro, o acaba de terminar una serie y le falta el aire. **Una app de voz que solo acepta voz es una app frágil.**

---

## 1. Las cuatro modalidades, con criterio

| Modalidad | Coste de implementar | Valor real | Veredicto |
|---|---|---|---|
| **Voz** | Alto (es el núcleo) | Alto | ✅ Núcleo del producto |
| **Texto** | ~1 h | **Alto** | ✅ **Imprescindible.** Ver §2 |
| **Foto** | ~2–3 h | **Muy alto** | ✅ La feature de lucimiento del proyecto (§3) |
| **Vídeo** | ~4–6 h | Medio | ⚠️ Solo si sobra el domingo (§4) |

Un principio que conviene decir en voz alta durante la entrevista: **añadir modalidades no es acumular features, es reducir fricción**. Cada una responde a un contexto de uso distinto del mismo usuario.

---

## 2. Texto — barato e imprescindible

Es la misma tubería sin el primer eslabón: el `MensajeEntrante` ya lleva `texto: str | None`, y `procesar_mensaje` simplemente **se salta el STT**.

```python
texto = msg.texto or await stt.transcribir(msg.audio, msg.audio_mime)
```

Una línea. Y te da tres cosas:

- **Accesibilidad** — usuarios con dificultades del habla, o entornos ruidosos y silenciosos.
- **Testabilidad** — puedes probar toda la lógica conversacional sin generar audio.
- **Una demo que no depende del micrófono** — si el evaluador abre tu app en un portátil sin permisos de micrófono, **sigue funcionando**. Este detalle solo puede salvarte la evaluación.

En la interfaz: campo de texto junto al botón de micrófono, siempre visible, no escondido tras un menú.

---

## 3. Fotos — la feature que se recuerda

Bedrock acepta imágenes de forma nativa en la Converse API. El coste de implementación es bajo y el efecto en una demo es enorme.

### 3.1 Casos de uso reales de running (no genéricos)

| Foto | Qué hace Koda | Por qué importa |
|---|---|---|
| **Pantalla del reloj tras entrenar** | Extrae distancia, tiempo y ritmo → llama a `registrar_entrenamiento` → confirma por voz | **El caso estrella.** Elimina el registro manual, que es donde el usuario abandona |
| **Inscripción o dorsal de la carrera** | Extrae nombre y fecha → crea el objetivo → propone plan | Onboarding en un gesto |
| **Captura de otra app** (Strava, Nike Run) | Igual que el reloj | Puente hacia apps que no vas a integrar por API |
| **Zapatillas desgastadas** | Comenta el desgaste y sugiere revisar los kilómetros acumulados | Simpático, secundario |

**El flujo del reloj, completo:** el usuario termina de correr, hace una foto a la pantalla del reloj y la manda sin escribir nada. Koda responde: *"¡Bien! 8,2 km en 47:30, ritmo de 5:47. Va justo con lo planeado para hoy. ¿Cómo te sentiste?"* — y lo deja registrado. Eso, en un vídeo de demo de 2 minutos, vale más que diez pantallas.

### 3.2 Implementación

Una imagen puede llegar sin texto. En ese caso el prompt lleva una instrucción implícita:

```python
if msg.imagenes and not texto:
    texto = ("El usuario envió una imagen sin texto. Interprétala en el contexto "
             "de su entrenamiento y actúa en consecuencia.")
```

Y una herramienta específica para no depender de que el modelo improvise el formato:

```python
extraer_datos_de_captura(
    distancia_km: float | None,
    duracion_seg: int | None,
    ritmo_seg_km: int | None,
    fecha: str | None,
    confianza: float,       # ← clave
)
```

**Si `confianza < 0.7`, Koda pregunta en vez de registrar.** *"Creo que leí 8,2 km en 47:30, ¿es correcto?"* Un sistema que sabe cuándo no está seguro es infinitamente mejor que uno que se inventa datos con aplomo. Dilo así en la entrevista.

### 3.3 Validación y privacidad (no es opcional)

| Control | Cómo |
|---|---|
| **Tamaño máximo** | 8 MB por imagen, 3 imágenes por mensaje |
| **Tipo real** | Comprobar los *magic bytes* con `filetype`/`Pillow`, **no la extensión ni el `Content-Type`** |
| **Re-encodear** | Abrir con Pillow y volver a guardar como JPEG: destruye cualquier payload incrustado |
| **⚠️ Eliminar EXIF** | Las fotos de móvil **llevan coordenadas GPS**. Guardar la foto del reloj de alguien con las coordenadas de su casa es una fuga de datos seria |
| **Redimensionar** | Máx. 1568 px en el lado largo antes de mandarla al modelo: menos tokens, menos coste, misma lectura |

```python
from PIL import Image

def sanear_imagen(bruto: BinaryIO) -> bytes:
    img = Image.open(bruto)
    img.verify()                       # detecta archivos corruptos o maliciosos
    img = Image.open(bruto)            # verify() consume el stream
    img = img.convert("RGB")           # descarta canales raros
    img.thumbnail((1568, 1568))
    salida = BytesIO()
    img.save(salida, format="JPEG", quality=85)   # sin EXIF: Pillow no lo copia por defecto
    return salida.getvalue()
```

Ese comentario sobre el EXIF es exactamente el tipo de detalle que un entrevistador de seguridad busca y casi nadie menciona.

---

## 4. Vídeo — ambicioso, opcional, con criterio

### El caso de uso que sí tiene sentido

**Análisis de técnica de carrera.** El usuario graba 10 segundos corriendo (o alguien lo graba) y Koda comenta cadencia aparente, aterrizaje del pie, postura del torso y braceo. Es una consulta real que los runners le hacen a sus entrenadores.

### Cómo, sin complicarte

**No mandes el vídeo entero al modelo.** Extrae fotogramas con `ffmpeg` y trátalos como imágenes:

```python
async def keyframes(video: Path, n: int = 6) -> list[bytes]:
    """Extrae n fotogramas repartidos y los devuelve como JPEG saneados."""
    # ffmpeg -i video -vf "fps=..,scale=1024:-1" -frames:v n salida_%02d.jpg
```

Ventajas: reutilizas **toda** la tubería de imágenes del §3, no dependes de que el modelo soporte vídeo, y el coste es predecible.

### Límites duros

- **10 segundos máximo, 25 MB.** Se rechaza con mensaje claro, no con un error genérico.
- **6 fotogramas máximo.** Más no aporta y multiplica el coste.
- Sin audio: se descarta la pista de audio del vídeo.

### ⚠️ Sé honesto contigo mismo sobre esto

El vídeo es **la peor relación valor/hora del proyecto**. Es la única feature marcada como opcional en el [plan de ejecución](07-PLAN-EJECUCION.md), y solo se toca el domingo si todo lo demás está cerrado. Si el domingo a las 18:00 los correos o el aislamiento no están terminados, **el vídeo se cae y se documenta en el Roadmap del README**.

Que sepas priorizar y recortar bajo presión es, literalmente, lo que se evalúa en una prueba con fecha límite.

---

## 5. La interfaz con todas las modalidades

```
┌─────────────────────────────┐
│  🐺 Koda              ⚙️    │
├─────────────────────────────┤
│                             │
│   ┌──────────────────────┐  │
│   │ Koda: ¿Cómo te fue   │  │
│   │ el rodaje de hoy?  ▶ │  │  ▶ = re-escuchar
│   └──────────────────────┘  │
│       ┌──────────────────┐  │
│       │ [📷 captura del  │  │  miniatura de la foto
│       │  reloj]          │  │
│       └──────────────────┘  │
│   ┌──────────────────────┐  │
│   │ Koda: ¡8,2 km en     │  │
│   │ 47:30! Justo en      │  │
│   │ plan. ¿Cómo te       │  │
│   │ sentiste?          ▶ │  │
│   └──────────────────────┘  │
│                             │
├─────────────────────────────┤
│ [📎] [ Escribe...    ] ( 🎤 )│  ← una sola barra
└─────────────────────────────┘
```

**Reglas de interacción:**

- El **micrófono** se mantiene pulsado para hablar (`pointerdown` / `pointerup`, no `click` — funciona igual con dedo y con ratón).
- El **clip** abre cámara o galería: `<input type="file" accept="image/*,video/*" capture="environment">`. El atributo `capture` abre la cámara trasera directamente en móvil.
- El **campo de texto** siempre visible, nunca detrás de un menú.
- Cada mensaje del coach lleva **texto y audio**: se lee o se escucha, decide el usuario.
- Mientras se sube una foto, **miniatura con barra de progreso**. Una subida sin feedback se percibe como una app rota.

---

## 6. Resumen de límites

| Entrada | Límite | Al superarlo |
|---|---|---|
| Audio | 60 s · 10 MB | *"Fue un poco largo, ¿me lo resumes?"* |
| Texto | 2 000 caracteres | Se trunca avisando |
| Imagen | 3 por mensaje · 8 MB c/u | Mensaje claro indicando el límite |
| Vídeo | 10 s · 25 MB · 6 fotogramas | Mensaje claro indicando el límite |
| Global | 30 mensajes/hora por runner | *"Vas muy rápido, respira 😄"* + `429` |

Todos los límites se validan **en el servidor**. La validación en el navegador es para la experiencia; la del servidor es la que te protege.

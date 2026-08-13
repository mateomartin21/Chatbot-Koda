# 05 · Memoria de conversaciones

> Uno de los dos puntos extra del reto. Mal hecho es meter todo el historial en el prompt hasta reventar contexto y presupuesto. Bien hecho son **tres capas con propósitos distintos** — y saber explicar esa distinción ya te separa del montón.

---

## 1. Por qué tres capas y no un historial

Un historial completo tiene tres problemas que se agravan con el tiempo:

1. **Coste** — cada mensaje reenvía toda la conversación. Crece cuadráticamente.
2. **Ruido** — al modelo le cuesta encontrar el dato relevante entre 200 mensajes de charla.
3. **Límite duro** — llega un día en que ya no cabe, y truncar por la mitad borra justo el contexto antiguo, que es el valioso.

La solución no es un truco: es **clasificar la información por su naturaleza y darle a cada tipo el almacenamiento que le corresponde**.

---

## 2. Las tres capas

### Capa 1 · Perfil estructurado — *hechos duros, siempre presentes*

Tablas `runners`, `objetivos`, `planes`, `sesiones`. Se inyecta como datos en cada llamada.

- **Barato:** ~200 tokens fijos.
- **Exacto:** si el runner dijo que corre 4 días, eso es un campo `INTEGER`, no una memoria difusa que el modelo pueda malinterpretar.
- **Regla:** todo dato que puedas modelar como columna, **modélalo como columna**. No uses el LLM como base de datos.

### Capa 2 · Ventana corta — *contexto inmediato*

Los últimos ~10 turnos, tal cual, de la tabla `conversaciones`.

- Para que la conversación fluya y los pronombres tengan referente: *"¿y ese día qué hago?"*.
- Límite fijo, no adaptativo. Simple y predecible.

### Capa 3 · Hechos duraderos — *lo que impresiona*

Tras cada conversación, una llamada barata a un modelo pequeño extrae hechos que trascienden la sesión y los guarda categorizados en `memoria_hechos`.

```json
[
  {"categoria": "lesion",       "hecho": "molestia en rodilla derecha al bajar cuestas", "confianza": 0.9},
  {"categoria": "preferencia",  "hecho": "prefiere correr por la mañana antes del trabajo", "confianza": 0.8},
  {"categoria": "contexto",     "hecho": "vive en Ciudad de México, 2240 m de altitud", "confianza": 0.95},
  {"categoria": "logro",        "hecho": "completó su primer 5K sin parar el 2 de agosto", "confianza": 1.0},
  {"categoria": "restriccion",  "hecho": "no puede entrenar los martes por clase", "confianza": 0.9}
]
```

**El efecto en el evaluador:** dos semanas después, el coach dice *"acuérdate de tu rodilla, hoy evitamos cuestas"*. Se siente mágico. Son unas 40 líneas de código.

---

## 3. Cómo se ensambla el contexto

```python
# application/contexto.py — el ÚNICO sitio que ensambla contexto del LLM
async def construir_contexto(runner_id: UUID) -> ContextoConversacion:
    perfil    = await repos.runners.obtener(runner_id)
    plan      = await repos.planes.activo(runner_id)
    proximas  = await repos.sesiones.proximas(runner_id, dias=7)
    recientes = await repos.conversaciones.ultimos(runner_id, limite=10)
    hechos    = await repos.memoria.vigentes(runner_id, limite=25)
    return ContextoConversacion(perfil, plan, proximas, recientes, hechos)
```

> ⚠️ **Todas las consultas llevan `runner_id`.** Esta función es la frontera de aislamiento descrita en [03-MULTIUSUARIO-Y-SEGURIDAD §4.3](03-MULTIUSUARIO-Y-SEGURIDAD.md). Es también el sitio donde se audita cualquier sospecha de fuga entre usuarios.

Presupuesto de tokens, aproximado:

| Capa | Tokens | Crece con el tiempo |
|---|---|---|
| System prompt | ~600 | No |
| Perfil + plan (capa 1) | ~300 | No |
| Últimos 10 turnos (capa 2) | ~800 | No (ventana fija) |
| Hechos vigentes (capa 3) | ~400 | Muy despacio |
| **Total** | **~2 100** | **Prácticamente constante** |

**Que el coste por mensaje sea constante aunque el usuario lleve un año usando la app** es el argumento entero de este diseño. Tenlo preparado.

---

## 4. Higiene de la memoria (lo que casi nadie hace)

Una memoria que solo acumula se pudre. Tres mecanismos:

### 4.1 Contradicciones

Si llega *"ya se me quitó lo de la rodilla"*, el hecho antiguo se marca `vigente = False` **en lugar de borrarlo**. Conservas la historia (útil para el resumen anual) y dejas de inyectar información falsa.

### 4.2 Deduplicación

Antes de insertar, se compara con los hechos existentes de la misma categoría. *"Prefiere correr en la mañana"* no debe guardarse cinco veces. Con normalización de texto basta; no necesitas embeddings para esto.

### 4.3 Caducidad por categoría

| Categoría | Vigencia |
|---|---|
| `lesion` | 90 días, salvo confirmación posterior |
| `preferencia` | Indefinida |
| `contexto` | Indefinida |
| `logro` | Indefinida (son el histórico) |
| `restriccion` | 180 días |

Una lesión de hace ocho meses ya no debería condicionar el plan de hoy.

---

## 5. Prompt de extracción

Vive en `app/prompts/extraccion_memoria.md`, versionado con el código. Ver [06-PROMPTS](06-PROMPTS.md) para el texto completo.

Puntos clave del diseño:

- Usa un **modelo pequeño y barato** (`nova-lite` o equivalente): es una tarea de clasificación, no de razonamiento.
- Se ejecuta **después** de responder al usuario, en segundo plano. **Nunca en el camino crítico**: el usuario no debe esperar por la extracción.
- Devuelve **JSON estricto validado con Pydantic**. Si no valida, se descarta y se registra. Una memoria vacía es mejor que una memoria corrupta.
- Prohibición explícita en el prompt: **no extraer datos clínicos ni diagnósticos**, solo información funcional de entrenamiento. *"Le molesta la rodilla al bajar cuestas"* sirve para adaptar la carga; un diagnóstico no le corresponde a Koda ([02 §6](02-DOMINIO-RUNNING.md)).

---

## 6. Escalado (para el README, no para esta semana)

Con un usuario de demo, traer los 25 hechos vigentes es óptimo. Con miles de hechos por usuario, la evolución natural es **embeddings + `pgvector`** para recuperar solo los relevantes a la conversación actual.

**No lo implementes esta semana.** Pero ponlo en el README como evolución: demuestra que sabes dónde está el límite de tu solución, que es una señal de criterio mucho mejor que implementarlo sin necesidad. Sobreingeniería y falta de visión son ambos errores; el punto medio es *"sé dónde se rompe y sé qué haría"*.

---

## 7. Cómo demostrar la memoria en la demo

En el vídeo de 2–3 minutos, la memoria hay que **enseñarla**, no contarla:

1. Primera conversación: el usuario menciona de pasada que le molesta la rodilla en bajadas.
2. Cierra la sesión. Vuelve a entrar.
3. Pregunta por el entrenamiento del domingo (que incluye cuestas).
4. Koda responde adaptando la sesión **y diciendo por qué**: *"como me contaste lo de la rodilla, cambié las cuestas por..."*.

Ese corte de 20 segundos vale más que un párrafo del README explicando la arquitectura de memoria.

# 08 · Convenciones

Reglas cortas para no tener que decidir dos veces lo mismo.

---

## Git

**Ramas**

```
main            siempre desplegable
feat/<algo>     una rama por bloque de trabajo
```

Con un solo desarrollador y 4 días, ramas cortas que se fusionan el mismo día. Nada de ramas que viven tres días.

**Mensajes de commit** — Conventional Commits, en español, explicando el *porqué*:

```
feat:     nueva funcionalidad
fix:      corrección de bug
refactor: cambio interno sin alterar comportamiento
test:     tests
docs:     documentación
chore:    tooling, configuración, dependencias
prompt:   cambios en app/prompts/
```

```
✅ feat: extraer hechos de memoria en segundo plano para no bloquear la respuesta
✅ fix: el token mágico se aceptaba dos veces al recargar el correo
❌ update
❌ cambios
❌ wip
```

**Commits pequeños y frecuentes.** Un commit por unidad de sentido. En una revisión de código, un commit de 40 archivos es imposible de evaluar y se lee como descuido.

---

## Python

| Regla | Detalle |
|---|---|
| **Type hints en todo** | Sin excepciones en `domain/` y `application/` |
| **Linter y formato** | `ruff check` + `ruff format`, en CI |
| **Nombres de dominio en español** | `PlanEntrenamiento`, `Sesion`, `Ritmo`. El dominio es el negocio, y el negocio se habla en español |
| **Nombres técnicos en inglés** | `Repository`, `Port`, `Adapter`, `Settings`. Son términos del oficio |
| **Sin `print`** | `logging` con formato estructurado |
| **Sin números mágicos** | Constantes con nombre en el módulo del dominio |
| **Dataclasses inmutables** | `@dataclass(frozen=True)` para value objects |
| **Excepciones propias** | `PlanNoViable`, `RunnerNoEncontrado`. Nunca `raise Exception("...")` |

**Async**: todo lo que toque red es `async`. Nada de `requests` bloqueante dentro de un endpoint de FastAPI — una sola llamada bloqueante congela el event loop para todos.

---

## Tests

```
tests/
├── unit/          dominio puro. Rápidos, sin red, sin BD
├── integration/   casos de uso con adaptadores falsos y BD en memoria
├── security/      aislamiento entre usuarios. Ver 03
└── fakes/         FakeSTT, FakeLLM, FakeTTS, FakeEmail, InMemoryRepos
```

**Regla no negociable: la suite completa corre sin internet y sin gastar un céntimo.** Si un test necesita AWS, está mal escrito.

Nombres de test que describen el comportamiento, no la función:

```python
✅ def test_maraton_en_seis_semanas_es_rechazado()
✅ def test_un_runner_no_ve_el_plan_de_otro()
❌ def test_generar_plan_2()
❌ def test_ok()
```

---

## API

| Convención | Valor |
|---|---|
| Prefijo | `/api/` |
| Rutas | Sustantivos en plural: `/api/mensajes`, `/api/planes` |
| Identidad | **Siempre** de la cookie de sesión, **nunca** del cuerpo |
| Errores | `{"error": {"codigo": "PLAN_NO_VIABLE", "mensaje": "..."}}` |
| Recursos ajenos | `404`, nunca `403` — no confirmes que existen |
| Validación | Modelos Pydantic en la frontera, siempre |

---

## Configuración y secretos

- Todo por variables de entorno vía `pydantic-settings`.
- `.env.example` **siempre actualizado** con todas las claves y valores de ejemplo (nunca reales).
- `.env` en `.gitignore` **desde el primer commit**.
- **Si se te escapa una credencial al repo: rótala.** Borrarla en un commit posterior no sirve de nada, sigue en el historial y en cualquier clon.

---

## Frontend

- Un solo `index.html` + `app.js` + `styles.css`. Sin build, sin framework — decisión consciente ([ADR-002](../adr/ADR-002-python-fastapi.md)).
- **Mobile-first**: los estilos base son los del móvil; las `media query` añaden escritorio, no al revés.
- Área táctil mínima **44 px**. Botón de micrófono ≥ 64 px.
- Contraste **AA** como mínimo.
- Todo texto que venga del servidor se inserta con `textContent`, **jamás con `innerHTML`**.
- Variables CSS para colores y espaciado. Nada de valores repetidos a mano.

---

## Documentación

- `docs/contexto/` — el porqué. Se actualiza cuando cambia una decisión.
- `docs/adr/` — decisiones puntuales, inmutables. Un ADR no se edita: se **supersede** con otro.
- `README.md` — la puerta de entrada para alguien que llega de cero.
- Comentarios en el código solo para explicar **por qué**, nunca **qué**. Si necesitas explicar qué hace, renombra.

---

## Definición de terminado

Copiada aquí a propósito, porque es la que más se olvida:

1. Funciona de punta a punta desde la interfaz
2. Tiene al menos un test
3. Falla con elegancia si el servicio externo se cae
4. Commiteado con un mensaje que explica el porqué
5. Si hubo una decisión discutible, hay un ADR

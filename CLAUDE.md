# Instrucciones para asistentes de IA en este repo

> Este archivo lo leen Claude Code y herramientas similares al abrir el proyecto. Mantenerlo actualizado ahorra explicar el contexto en cada sesión.

## Antes de tocar nada

Lee [`docs/contexto/00-CONTEXTO.md`](docs/contexto/00-CONTEXTO.md). Da todo el contexto en 5 minutos y enlaza al resto.

## Qué es este proyecto

Koda: web app de voz que funciona como entrenador personal de running. Es una **prueba técnica con fecha de entrega el 17 de agosto de 2026**, así que se evalúan las buenas prácticas y la calidad de las decisiones, no la cantidad de features.

## Reglas no negociables

1. **`app/domain/` no importa nada externo.** Ni `boto3`, ni `sqlalchemy`, ni `fastapi`, ni `requests`. Hay un test que lo comprueba: `tests/unit/test_arquitectura.py`.
2. **Las reglas de entrenamiento van en `app/domain/training/`**, nunca en un prompt ni en un endpoint. El LLM conversa; el dominio calcula.
3. **`runner_id` sale siempre del JWT**, nunca del cuerpo, la query o una cabecera. Si ves un `runner_id` llegando del cliente, es un IDOR.
4. **Ningún repositorio consulta datos personales sin `runner_id` en la firma.**
5. **La suite de tests corre sin internet y sin gastar créditos.** Si un test necesita AWS, está mal escrito — usa los dobles de `tests/fakes/`.
6. **Los prompts van en `app/prompts/*.md`**, nunca como cadenas dentro del código Python.
7. **Nada de secretos en el repo.** `.env` está en `.gitignore` desde el primer commit.

## Al añadir una dependencia externa

Siempre por un puerto:

1. Define la interfaz en `app/domain/ports/`
2. Implementa el adaptador en `app/infrastructure/`
3. Ensámblalo en `app/container.py` — es el **único** sitio que conoce las implementaciones concretas
4. Escribe un doble en `tests/fakes/`

## Al tomar una decisión discutible

Escribe un ADR en `docs/adr/` siguiendo el formato de [`docs/adr/README.md`](docs/adr/README.md). **Las consecuencias negativas son obligatorias.**

## Convenciones

Están en [`docs/contexto/08-CONVENCIONES.md`](docs/contexto/08-CONVENCIONES.md). Resumen:

- Nombres de dominio en español (`PlanEntrenamiento`, `Ritmo`), términos técnicos en inglés (`Repository`, `Port`)
- Type hints en todo · `ruff` para lint y formato
- Commits con Conventional Commits en español, explicando el porqué
- Tests con nombres que describen comportamiento: `test_maraton_en_seis_semanas_es_rechazado`
- `async` para todo lo que toque red — nada bloqueante dentro de un endpoint

## Comandos

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload      # servidor de desarrollo
pytest                             # suite completa
pytest tests/security -v           # aislamiento entre usuarios
ruff check . ; ruff format .       # lint y formato
alembic revision --autogenerate -m "..."   # nueva migración
alembic upgrade head               # aplicar migraciones
python scripts/smoke_aws.py        # comprobar que AWS responde
```

## Contexto de plazo

Consulta [`docs/contexto/07-PLAN-EJECUCION.md`](docs/contexto/07-PLAN-EJECUCION.md) antes de proponer trabajo nuevo. Hay una lista de prioridades explícita y una lista de lo que **no** se hace. **No propongas refactorizaciones de código que ya funciona, ni features fuera de esa lista.** Congelar el alcance a tiempo es parte de lo que se está evaluando.

## Estilo de colaboración

El autor prefiere **entender lo que se construye**, no recibir código terminado sin contexto. Explica el porqué de cada decisión, propón los comandos para que los ejecute él, y señala los riesgos y las alternativas descartadas.

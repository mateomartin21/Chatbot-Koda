# ADR-002 · Python + FastAPI, frontend sin framework

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

Hay que elegir lenguaje y framework con 4 días de plazo. El autor tiene más experiencia en **C# / ASP.NET Core** (arquitectura hexagonal, EF Core, xUnit, ADRs) que en Python, y también había explorado **n8n** como opción sin código.

## Decisión

**Python 3.12 + FastAPI** para el backend. **HTML + CSS + JavaScript vanilla** para el frontend, sin framework ni paso de build.

## Alternativas consideradas

**C# / ASP.NET Core.** Es el terreno más fuerte del autor, y la tentación era real. Descartado porque los SDKs de voz e IA son *first-class* en Python: `boto3`, `amazon-transcribe` y los ejemplos de Bedrock están escritos para Python. En .NET, varias integraciones habría que hacerlas por HTTP crudo, y ese tiempo no existe en un plazo de 4 días.

**n8n.** Descartado por una razón de fondo: este proyecto tiene lógica de dominio real (cálculo de ritmos, progresión de cargas, viabilidad de planes), memoria estructurada y necesidad de tests. En n8n eso queda enterrado en nodos que no se pueden versionar con sentido, ni testear, ni revisar en un *pull request*. **Siendo una prueba técnica, no se puede defender una arquitectura que no tiene código que enseñar.**

**React / Vue en el frontend.** Descartado: montar el proyecto, el build y el despliegue cuesta horas que salen directamente del dominio. Un `index.html` bien hecho, responsive y accesible se ve **mejor** que un React a medio terminar.

## Consecuencias

### Positivas

- Ecosistema de IA nativo: menos código de pegamento, más ejemplos disponibles.
- `async` de serie, que encaja con una app que es E/S pura (esperar a AWS todo el rato).
- El criterio de arquitectura (hexagonal, DI, Strategy, ADRs, tests con dobles) se traslada íntegro desde .NET. **Demostrar que tu criterio no depende del lenguaje vale más que el lenguaje.**
- Frontend sin build: se despliega copiando archivos, y no hay `node_modules` que puedan romperse la noche antes de entregar.

### Negativas

- El autor es **menos veloz en Python que en C#**, y bajo presión eso se nota. Se compensa con tipado estricto y `ruff` en CI.
- Sin framework de frontend, el estado de la interfaz se maneja a mano. Con más pantallas esto se volvería inmanejable — es una decisión válida para el tamaño **de este** proyecto, no una postura general.
- Python no tiene la seguridad de tipos en tiempo de compilación de C#. Los type hints ayudan, pero no son lo mismo.

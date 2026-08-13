# ADR-003 · Arquitectura hexagonal para aislar los proveedores de IA

**Estado:** Aceptado
**Fecha:** 2026-08-13

## Contexto

Koda depende de **cuatro servicios externos volátiles**: Amazon Transcribe, Bedrock, Polly y SES. Los modelos de IA se renombran, se deprecan y cambian de precio cada pocos meses. Además, al iniciar el proyecto **no existía todavía una cuenta de AWS**, de modo que había una probabilidad real de tener que cambiar de proveedor a mitad de desarrollo.

Con 4 días de plazo, la tentación evidente es llamar a `boto3` directamente desde los endpoints.

## Decisión

**Arquitectura hexagonal (puertos y adaptadores).** El dominio define interfaces (`STTPort`, `LLMPort`, `TTSPort`, `EmailPort`, `StoragePort`, repositorios) y no importa ninguna librería externa. Los adaptadores concretos viven en `infrastructure/` y se ensamblan en un único *composition root* (`container.py`).

Un test automático verifica que `app/domain/` no importe `boto3`, `sqlalchemy`, `fastapi` ni `requests`.

## Alternativas consideradas

**Llamar a los SDKs directamente desde los casos de uso.** Más rápido de escribir el primer día. Descartado por dos consecuencias concretas, no teóricas:

1. **Los tests exigirían red y créditos.** Cada ejecución de la suite costaría dinero y segundos. En un proyecto de 4 días con muchas iteraciones, eso significa dejar de correr los tests — y entonces no hay tests.
2. **No habría plan B.** Si AWS no se desbloqueaba, migrar habría exigido tocar todos los casos de uso.

**Arquitectura en capas clásica (controlador → servicio → repositorio).** Ordena, pero no invierte la dependencia: los servicios siguen conociendo los SDKs. No resuelve el problema real.

## Consecuencias

### Positivas

- **La suite de tests corre sin internet y sin coste**, con `FakeSTT`, `FakeLLM`, `FakeTTS`.
- **La arquitectura es la mitigación del riesgo principal del proyecto.** El plan B (Groq + Gemini + Resend) cuesta cambiar cuatro líneas en `container.py` en lugar de reescribir la aplicación.
- Permite tener **dos adaptadores de STT a la vez** (Transcribe y Whisper) y compararlos en latencia y calidad — un dato medido que contar en la entrevista.
- El dominio se puede leer y revisar sin saber nada de AWS.

### Negativas

- **Más archivos y más indirección** para el mismo comportamiento. En un proyecto de este tamaño es, objetivamente, más código del mínimo necesario.
- **Riesgo de abstracción prematura:** si un puerto se diseña calcando la API de un proveedor concreto, la abstracción es falsa y estorba. Se mitiga definiendo los puertos desde la necesidad del dominio (*"convierte audio en texto"*), no desde la firma del SDK.
- Para un desarrollador que llega nuevo, hay una **curva de lectura** antes de encontrar dónde ocurre algo. Este documento y [01-ARQUITECTURA](../contexto/01-ARQUITECTURA.md) existen justamente para pagar esa deuda.

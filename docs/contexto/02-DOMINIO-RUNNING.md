# 02 · Dominio de running

> Esta es la sección que decide si el proyecto se lee **junior o senior**. Aquí vive el conocimiento real de entrenamiento, en código determinista y testeable. El LLM no participa en estos cálculos: solo los explica.

---

## 1. Las reglas que van en código

| # | Regla | Qué significa | Dónde vive |
|---|---|---|---|
| R1 | **Progresión del 10 %** | El volumen semanal no sube más de ~10 % sobre la semana anterior | `plan_*.py` |
| R2 | **Polarización 80/20** | ~80 % del volumen a intensidad fácil, ~20 % a intensidad alta | `plan_*.py` |
| R3 | **Semana de descarga** | Cada 3–4 semanas se recorta el volumen ~30 % para asimilar la carga | `plan_*.py` |
| R4 | **Tapering** | Las últimas 2–3 semanas se baja el volumen manteniendo algo de intensidad | `plan_*.py` |
| R5 | **Ritmos derivados** | De una marca reciente salen todos los ritmos de entrenamiento | `paces.py` |
| R6 | **Mínimos por distancia** | Si no hay semanas suficientes, el sistema **se niega** y propone alternativa | `plan_*.py` |
| R7 | **Al menos un día de descanso** | Nunca se programan 7 días de carrera a la semana para un principiante | `plan_*.py` |
| R8 | **La tirada larga tiene techo** | No más del ~35 % del volumen semanal en una sola sesión | `plan_*.py` |

> **R6 es la regla estrella.** Un sistema que sabe decir *"no, preparar un maratón en 6 semanas desde cero es peligroso; hagamos un 21K y apuntamos al maratón en marzo"* demuestra que entendiste el dominio y no solo la API. Que el rechazo sea explícito, con alternativa y con explicación.

---

## 2. Cálculo de ritmos (`paces.py`)

### 2.1 Predecir el tiempo en otra distancia — fórmula de Riegel

```
T₂ = T₁ × (D₂ / D₁) ^ 1.06
```

Donde `T₁` es el tiempo en una distancia conocida `D₁`, y `T₂` el tiempo estimado en `D₂`. El exponente 1.06 es el valor clásico de Peter Riegel.

```python
def predecir_tiempo(t1_seg: float, d1_km: float, d2_km: float) -> float:
    """Predice el tiempo en d2 a partir de una marca en d1 (Riegel)."""
    if t1_seg <= 0 or d1_km <= 0 or d2_km <= 0:
        raise ValorInvalido("Distancias y tiempos deben ser positivos")
    return t1_seg * (d2_km / d1_km) ** 1.06
```

**Limitación honesta que debes documentar:** Riegel sobreestima el rendimiento en distancias muy largas para corredores con poca base. Para el maratón se aplica un factor de corrección conservador según el nivel del runner. Reconocer los límites de tu propio modelo es exactamente lo que se espera de un ingeniero.

### 2.2 Zonas de ritmo

A partir del **ritmo umbral** (aproximadamente el ritmo que el runner puede sostener una hora) se derivan las zonas:

| Zona | Ritmo relativo al umbral | Para qué sirve |
|---|---|---|
| **Fácil / rodaje** | umbral + 60 a 90 s/km | Base aeróbica. Es el 80 % del volumen |
| **Tirada larga** | umbral + 45 a 75 s/km | Resistencia. La sesión clave de 21K y 42K |
| **Tempo / umbral** | umbral ± 5 s/km | Elevar el umbral de lactato |
| **Intervalos** | umbral − 15 a 25 s/km | Potencia aeróbica (VO₂ máx) |
| **Ritmo objetivo** | el ritmo de la carrera meta | Que las piernas memoricen el ritmo |

```python
@dataclass(frozen=True)
class ZonasRitmo:
    facil: Ritmo
    larga: Ritmo
    tempo: Ritmo
    intervalos: Ritmo
    objetivo: Ritmo
```

`Ritmo` es un *value object* inmutable en segundos por kilómetro, con `__str__` que devuelve `"5:42/km"`. Nunca pases ritmos como float suelto: es la clase de descuido que produce bugs de unidades.

### 2.3 Si no hay marca reciente

Muchos principiantes no tienen ninguna. En ese caso se estima por **nivel autodeclarado + minutos que aguanta corriendo sin parar**, y el plan arranca conservador. Se marca `ritmos_estimados = True` para que el coach lo diga en voz alta: *"esto es una estimación, la ajustamos tras tu primera semana"*. **Transparencia sobre la incertidumbre.**

---

## 3. Estructura de los planes

### 3.1 Mínimos y forma por distancia (R6)

| Distancia | Semanas mín. | Semanas típicas | Días/semana | Tirada larga final | Notas |
|---|---|---|---|---|---|
| **5K** | 6 | 8 | 3–4 | 8–10 km | Ideal para principiantes absolutos |
| **10K** | 8 | 10–12 | 3–5 | 12–14 km | Requiere poder correr 20–30 min seguidos |
| **21K** | 12 | 14–16 | 4–5 | 18–19 km | Requiere base de ~20 km/semana |
| **42K** | 16 | 18–20 | 4–6 | 30–32 km | Requiere haber completado un 21K |

Si `semanas_disponibles < semanas_minimas`, la estrategia **lanza `PlanNoViable`** con una alternativa concreta. El caso de uso la traduce en una respuesta conversacional; no es un error técnico, es una decisión de entrenamiento.

### 3.2 Estructura de una semana tipo (10K, nivel intermedio)

| Día | Sesión |
|---|---|
| Lunes | Descanso o cruzado |
| Martes | Series: 6 × 800 m a ritmo de intervalos, 2 min de trote entre repeticiones |
| Miércoles | Rodaje fácil 6 km |
| Jueves | Tempo: 20 min continuos a ritmo umbral |
| Viernes | Descanso |
| Sábado | Rodaje fácil 5 km |
| Domingo | Tirada larga 12 km |

### 3.3 Patrón Strategy

```python
# domain/training/strategy.py
class EstrategiaPlan(ABC):
    @abstractmethod
    def distancia(self) -> Distancia: ...

    @abstractmethod
    def semanas_minimas(self) -> int: ...

    @abstractmethod
    def generar(self, runner: Runner, objetivo: Objetivo) -> PlanEntrenamiento: ...


# domain/training/factory.py
_ESTRATEGIAS: dict[Distancia, type[EstrategiaPlan]] = {
    Distancia.K5:  Plan5K,
    Distancia.K10: Plan10K,
    Distancia.K21: Plan21K,
    Distancia.K42: Plan42K,
}

def estrategia_para(distancia: Distancia) -> EstrategiaPlan:
    return _ESTRATEGIAS[distancia]()
```

Añadir un plan de ultra mañana = una clase nueva y una entrada en el diccionario. **Cero cambios en el resto** (Open/Closed). Ver [ADR-006](../adr/ADR-006-dominio-determinista.md).

---

## 4. Modelo de datos

> ⚠️ **Toda tabla con datos de usuario lleva `runner_id` y está indexada por él.** Ver [03-MULTIUSUARIO-Y-SEGURIDAD](03-MULTIUSUARIO-Y-SEGURIDAD.md).

```
runners           id(uuid) · email(unique) · nombre · edad · nivel · dias_disponibles
                  zona_horaria · marca_distancia_km · marca_tiempo_seg
                  creado_en · ultimo_acceso · activo

objetivos         id · runner_id → · distancia(5|10|21|42) · fecha_carrera
                  nombre_carrera · tiempo_meta_seg · estado(activo|completado|abandonado)

planes            id · runner_id → · objetivo_id → · semanas · generado_en
                  version · ritmos_estimados(bool) · zonas(json)

sesiones          id · plan_id → · runner_id → · semana · dia_semana
                  tipo(facil|series|tempo|largo|descanso|cruzado)
                  distancia_km · duracion_min · ritmo_objetivo_seg_km
                  descripcion · fecha_programada · completada

registros         id · runner_id → · sesion_id →(nullable) · fecha
                  distancia_km · duracion_seg · esfuerzo_percibido(1-10)
                  notas · fuente(voz|texto|foto)

conversaciones    id · runner_id → · rol(user|assistant)
                  contenido · modalidad(voz|texto|imagen|video)
                  adjuntos(json) · audio_key · creado_en

memoria_hechos    id · runner_id → · categoria(lesion|preferencia|contexto|logro|restriccion)
                  hecho · confianza(0-1) · creado_en · vigente(bool)

recordatorios     id · runner_id → · tipo(diario|checkin|semanal)
                  hora_local · activo · ultima_ejecucion

tokens_acceso     id · runner_id → · token_hash · expira_en · usado_en · ip_solicitud
```

### Índices que no puedes olvidar

```sql
CREATE INDEX idx_conversaciones_runner_fecha ON conversaciones (runner_id, creado_en DESC);
CREATE INDEX idx_hechos_runner_vigente       ON memoria_hechos (runner_id, vigente);
CREATE INDEX idx_sesiones_runner_fecha       ON sesiones (runner_id, fecha_programada);
CREATE UNIQUE INDEX idx_runners_email        ON runners (lower(email));
```

Ese `lower(email)` evita que `Mateo@x.com` y `mateo@x.com` se registren como dos personas distintas. Detalle pequeño, se nota.

---

## 5. Qué testear del dominio (y por qué aquí sí vale TDD)

El dominio es **funciones puras sin E/S**: los tests son instantáneos y no cuestan nada. Escríbelos primero.

```python
def test_riegel_predice_10k_desde_5k():
    t = predecir_tiempo(t1_seg=25*60, d1_km=5, d2_km=10)
    assert 51*60 < t < 53*60          # ~52 min, coherente con la fórmula

def test_maraton_en_seis_semanas_es_rechazado():
    with pytest.raises(PlanNoViable) as e:
        estrategia_para(Distancia.K42).generar(runner_novato, objetivo_en_6_semanas)
    assert e.value.alternativa.distancia == Distancia.K21

def test_el_volumen_nunca_sube_mas_del_diez_por_ciento():
    plan = estrategia_para(Distancia.K10).generar(runner, objetivo)
    for previa, actual in pares(volumen_por_semana(plan)):
        assert actual <= previa * 1.10 + 0.01

def test_hay_semana_de_descarga_cada_cuatro():
    plan = estrategia_para(Distancia.K21).generar(runner, objetivo)
    assert any(es_descarga(s) for s in plan.semanas[3:5])

def test_el_taper_reduce_volumen_antes_de_la_carrera():
    plan = estrategia_para(Distancia.K42).generar(runner, objetivo)
    assert volumen(plan.semanas[-1]) < volumen(plan.semanas[-4]) * 0.6

def test_ningun_principiante_corre_siete_dias():
    plan = estrategia_para(Distancia.K5).generar(runner_novato, objetivo)
    for semana in plan.semanas:
        assert sum(1 for s in semana.sesiones if s.tipo != TipoSesion.DESCANSO) <= 4
```

Seis tests que **demuestran que el sistema entiende de running**. Valen más en una revisión que cincuenta tests de getters.

---

## 6. Advertencia de responsabilidad

Koda da orientación de entrenamiento, **no consejo médico**. El prompt del sistema ([06-PROMPTS](06-PROMPTS.md)) incluye una instrucción explícita: ante dolor persistente, mareos, dolor en el pecho o una lesión, el coach recomienda parar y consultar a un profesional de la salud, y **no** intenta diagnosticar ni sugerir tratamientos. Los hechos de categoría `lesion` en la memoria sirven para **adaptar la carga** (evitar cuestas, reducir volumen), nunca para dar un diagnóstico.

Esto también se refleja en la interfaz con un aviso discreto en el pie. Es una decisión de producto responsable y, en una entrevista, demuestra que piensas en el usuario real y no solo en el código.

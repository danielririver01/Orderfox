# Copilot VZ — Analista de Negocios IA

## Visión General

Copilot VZ es el analista de negocios integrado de Velzia. Es un asistente conversacional que permite a los dueños de restaurantes entender y mejorar su negocio mediante consultas en lenguaje natural, sin necesidad de saber SQL ni interpretar gráficos por sí mismos.

**Arquitectura:** Híbrida — combina consultas directas a la base de datos (SQL) para respuestas inmediatas con llamadas a DeepSeek para análisis profundos. Esto minimiza costos de API y maximiza velocidad.

---

## Flujo de una Consulta

```
Usuario escribe mensaje
        │
        ▼
[1] Guard → ¿Pregunta por datos de otro restaurante?
        │                       │ Sí → Scope guard (sin crédito, sin LLM)
        │ No
        ▼
[2] Clasificador → ¿Es consulta rápida o análisis profundo?
        │                       │ Quick → SQL directo + gráfica (GRATIS)
        │                       │ Deep → Pasa a [3]
        ▼
[3] Token check → ¿Conversación ya pagada o usuario tiene créditos?
        │                       │ Sin créditos → "No tienes créditos"
        │                       │ Pagada → Pasa a [4] sin descontar
        │                       │ Primera vez → Descarta 1 crédito, marca como pagada
        ▼
[4] Prompt builder → Arma contexto JSON + historial + system prompt
        │
        ▼
[5] LLM Service → Llama a DeepSeek API
        │
        ▼
[6] Parse → Extrae texto + gráfica + título del JSON de respuesta
        │
        ▼
[7] Chart sanitizer → Limpia datos corruptos de la gráfica
        │
        ▼
[8] Respuesta al usuario + guardado en BD
```

### Tipos de Respuesta

| Tipo | Descripción | ¿Pasa por DeepSeek? | ¿Cuesta crédito? |
|------|-------------|---------------------|------------------|
| **quick** | Consulta SQL directa (ventas, productos, ticket promedio) | No | No |
| **analysis** | Análisis profundo con IA (recomendaciones, proyecciones) | Sí | Sí (1er análisis de la conversación) |
| **scope_guard** | Rechazo amable cuando pregunta por datos de otro restaurante | No | No |
| **no_credits** | Tarjeta informativa cuando no hay créditos disponibles | No | No |
| **subscription_required** | Suscripción vencida tras período de gracia | No | No |
| **no_data_window** | No hay datos en la ventana solicitada | No | No |
| **calc_impact** | Proyección de impacto basada en datos reales | No | No |
| **empty_state** | Onboarding: no hay catálogo o no hay ventas aún | No | No |

---

## Estructura del Código

```
app/routes/insights.py                      — Blueprint Flask (web + API)
app/services/insights/
├── __init__.py                             — Service container
├── prompt_builder.py                       — System prompt + armado de mensajes
├── llm_service.py                          — Única capa que conoce DeepSeek API
├── classifier.py                           — Clasificador híbrido (regex + contexto)
├── data_service.py                         — Consultas SQL + contexto de datos
├── chart_service.py                        — Generación y limpieza de gráficas
├── context_manager.py                      — Estimación de tokens y compresión
├── conversation_service.py                 — CRUD de conversaciones y mensajes
├── event_engine.py                         — Motor de eventos automáticos
└── event_templates.py                      — Templates de eventos predefinidos

app/static/js/insights.js                   — Frontend vanilla JS (chat)
app/template/dashboard/insights.html         — Página principal del chat
app/template/dashboard/legal/sections/copilot.html — Sección de ayuda legal
```

---

## Componentes Clave

### 1. Clasificador (`classifier.py`)

Determina si una consulta es **quick** o **analysis** usando:

- **Pistas explícitas**: Palabras como "gráfica", "chart", "visualizar" fuerzan `analysis`
- **Intenciones predefinidas**: `sales_today`, `top_product`, `avg_ticket`, `compare_months`, etc.
- **Ventana temporal**: Detecta "hoy", "ayer", "este mes", "los últimos X días"
- **Guard de alcance**: Detecta si el usuario pregunta por datos de un restaurante ajeno por nombre

```python
cls = classifier.classify("cuánto vendí ayer?")
# → {'level': 'quick', 'intent': 'sales_yesterday', 'window': 1}
```

### 2. Data Service (`data_service.py`)

Capa de acceso a datos que construye el **contexto JSON** que se envía al LLM. Incluye:

- Resumen de ventas (totales, tickets, productos)
- Top productos por ingresos y cantidad
- Desglose por día de la semana
- Proyecciones y estimaciones
- Etapa de madurez del restaurante (nivel 0-3)
- Sugerencias de bienvenida y seguimiento

El contexto se construye con `build_context(restaurant_id, days=90)` y se serializa a JSON. El LLM **nunca** hace cálculos propios; solo interpreta los datos que Flask ya procesó.

### 3. Prompt Builder (`prompt_builder.py`)

Construye el system prompt con reglas estrictas:

- **Personalidad**: Copilot VZ, analista de Velzia, tono colombiano cercano
- **Prohibición**: No inventar cifras, no analizar restaurantes ajenos
- **Formato**: Las gráficas se devuelven como JSON estructurado
- **Regla 12 (identidad)**: Nunca confundir el nombre del restaurante con la identidad del asistente

La versión del prompt (`PROMPT_VERSION = "v1.3"`) se guarda en cada conversación para mantener compatibilidad histórica.

### 4. LLM Service (`llm_service.py`)

Único punto de contacto con DeepSeek. Configurable vía variables de entorno:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | API key de DeepSeek |
| `DEEPSEEK_API_URL` | `https://api.deepseek.com/v1/chat/completions` | URL base |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Modelo (chat vs reasoner) |

Recomendación: usar `deepseek-v4-flash`. Es 10x más barato que `deepseek-reasoner` y suficiente para análisis de negocio.

### 5. Context Manager (`context_manager.py`)

Gestiona el uso de tokens del prompt completo. Características:

- **Estimación**: ~3.5 chars/token para español, ~2 chars/token para JSON
- **Límite**: 12K tokens de input máximo
- **Compresión en 2 fases**:
  - **≥80%**: Genera resumen de la conversación vía DeepSeek (1 request extra)
  - **≥85%**: Activa modo comprimido (resumen + últimos 5 mensajes como historial)
- **Metadata**: Toda la info de compresión se guarda en `metadata_json` de la conversación (sin migraciones ni borrado de mensajes)

### 6. Chart Service (`chart_service.py`)

Genera gráficas tipo `line`, `bar`, `doughnut` y `pie` a partir de los datos SQL. Incluye:

- `chart_for_intent()`: Mapea intención + resultado a tipo de gráfica
- `clean_chart()`: Sanea datos corruptos que el LLM pueda generar
- `followup_suggestions()`: Sugerencias contextuales post-respuesta

### 7. Conversation Service (`conversation_service.py`)

CRUD completo de conversaciones y mensajes:

- `list_conversations(user_id, limit=50)`: Lista con paginación
- `create_conversation()`: Nueva conversación
- `get_messages()`: Mensajes en orden cronológico
- `add_message()`: Guarda mensaje con metadata
- `find_draft()`: Reutiliza borradores vacíos
- `set_pinned()`: Anclar conversaciones
- `delete_messages_after()`: Para regeneración/reintento

### 8. Motor de Eventos (`event_engine.py`)

Genera insights automáticos sin intervención del usuario:

- Escanea datos del restaurante periódicamente (APScheduler)
- Detecta patrones: picos de ventas, días flojos, productos estrella
- Crea eventos con prioridad (alta/media/baja)
- Los eventos aparecen en el dashboard y se pueden consumir (→ nueva conversación)

---

## API Endpoints

Todas las rutas bajo `/insights/`. Las rutas API bajo `/insights/api/`.

### Web

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/insights/` | Página principal del chat |

### API — Conversaciones

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/insights/api/conversations` | Listar conversaciones del usuario |
| POST | `/insights/api/conversations` | Crear conversación |
| POST | `/insights/api/conversations/draft` | Obtener borrador vacío o crear uno |
| GET | `/insights/api/conversations/<id>` | Obtener conversación con mensajes |
| DELETE | `/insights/api/conversations/<id>` | Eliminar conversación |
| PUT | `/insights/api/conversations/<id>` | Renombrar conversación |
| PATCH | `/insights/api/conversations/<id>/pin` | Fijar/quitar fijo |

### API — Mensajes

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/insights/api/conversations/<id>/messages` | Enviar mensaje (corazón del sistema) |

### API — Utilidades

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/insights/api/onboarding` | Tarjeta de onboarding según nivel de datos |
| GET | `/insights/api/events/pending` | Eventos activos pendientes |
| POST | `/insights/api/events/<id>/consume` | Consumir evento (abrir conversación) |
| POST | `/insights/api/events/<id>/dismiss` | Descartar evento |

### Formato de Respuesta

```json
{
  "success": true,
  "type": "quick|analysis|no_credits|...",
  "content": "Texto de la respuesta...",
  "chart": { /* gráfica opcional */ },
  "metadata": {
    "type": "quick|analysis",
    "intent": "sales_today",
    "window": 1,
    "credits_used": 0,
    "model": "sql",
    "execution_ms": 45,
    "suggestions": ["Sugerencia 1", "Sugerencia 2"]
  },
  "context_usage": 34,
  "assistant_message_id": 123
}
```

---

## Sistema de Contexto

### Anillo de Contexto

El frontend muestra un anillo SVG junto al botón de enviar indicando el porcentaje de uso del contexto variable (historial, no incluye system prompt + contexto JSON).

- **0-79%**: Verde
- **80-84%**: Amarillo (se genera resumen en segundo plano)
- **85-100%**: Rojo (modo comprimido activo)

### Compresión

Cuando el uso de contexto supera el 80%, se activa la compresión en 2 fases:

1. **≥80%**: Se genera un resumen de la conversación usando DeepSeek (un request extra, pero reduce el tamaño del historial drásticamente)
2. **≥85%**: Se activa el modo comprimido. El historial se reemplaza por el resumen + los últimos 5 mensajes

La metadata de compresión se almacena en `metadata_json` de la conversación. No se borran mensajes.

---

## Sistema de Tokens (Créditos)

Los usuarios tienen un `AITokenWallet` con créditos internos de Velzia:

| Plan | Tokens por mes | Reset |
|------|---------------|-------|
| Trial | 50 (de por vida) | No |
| Básico | 100 | Mensual |
| Pro | 300 | Mensual |
| Elite | Ilimitado | — |

**Reglas:**
- Las consultas rápidas (SQL) no consumen créditos
- El primer análisis profundo de cada conversación consume 1 crédito
- Los seguimientos dentro de la misma conversación no consumen créditos
- El consumo real de DeepSeek corre por cuenta de Velzia (~$0.003 por análisis)

---

## Onboarding Inteligente

El sistema detecta la madurez de datos del restaurante y muestra diferentes estados:

| Nivel | Productos | Órdenes | Qué se muestra |
|-------|-----------|---------|----------------|
| 0 | 0 | 0 | Guía para crear el primer producto/categoría |
| 1 | >0 | 0 | Guía para registrar una venta de prueba |
| 2 | >0 | 1-20 | Estado vacío con nota de aprendizaje |
| 3 | >0 | >20 | Bienvenida completa con sugerencias |

Las sugerencias de bienvenida son dinámicas según el nivel:
- **Nivel 0**: "Crear mi primer producto", "¿Qué puede hacer Copilot?"
- **Nivel 1**: "Registrar una venta", "Tips para empezar"
- **Nivel 2**: "Analiza mis ventas", "Producto estrella"
- **Nivel 3**: 8 opciones rotativas incluyendo proyecciones, comparativas, etc.

---

## Eventos Automáticos

El `event_engine.py` escanea periódicamente los datos de cada restaurante y genera insights proactivos:

### Ciclo de Vida de un Evento

1. **Detección**: El escaneo encuentra un patrón (ej: "ventas bajas los domingos")
2. **Creación**: Se guarda como `CopilotBusinessEvent` con prioridad y template
3. **Notificación**: Aparece en el dashboard del usuario como tarjeta
4. **Consumo**: El usuario hace clic → se abre una conversación nueva con el análisis precargado
5. **Descarte**: El usuario lo cierra si no le interesa

### Tipos de Eventos

Definidos en `event_templates.py` con:
- `KIND_PRIORITY`: Orden de importancia
- `KIND_COOLDOWN`: Tiempo mínimo entre eventos del mismo tipo

---

## Configuración

### Variables de Entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | API key de DeepSeek |
| `DEEPSEEK_API_URL` | `https://api.deepseek.com/v1/chat/completions` | URL de la API |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Modelo a usar |

### Modelo Recomendado

`deepseek-v4-flash` (DeepSeek V4 Flash). Relación costo/velocidad ideal para análisis de negocio. Costo estimado: ~$0.14/M tokens input, ~$0.28/M tokens output.

---

## Frontend (insights.js)

El chat es vanilla JavaScript (~1550 líneas) con:

- **Modo bienvenida/chat**: Pantalla de inicio con sugerencias vs conversación activa
- **Burbujas**: Mensajes de usuario (derecha) y asistente (izquierda) con badges
- **Gráficas**: Renderizadas con Chart.js 4.4.1 (CDN)
- **Anillo de contexto**: SVG que muestra uso de tokens en tiempo real
- **Disclaimer**: "Copilot VZ puede cometer errores" (se muestra una vez por conversación)
- **Regeneración**: Botón para regenerar la última respuesta
- **Edición**: Editar mensaje enviado y bifurcar la conversación
- **Sugerencias contextuales**: Chips post-respuesta según la intención detectada
- **Onboarding**: Tarjetas interactivas para guiar al usuario paso a paso

---

## Mantenimiento y Evolución

### Agregar una Nueva Intención

1. Agregar el intent en `classifier.py` (`_QUICK_INTENTS` + regex)
2. Agregar la lógica SQL en `data_service.py` (`handle_quick()` + `build_context()`)
3. Agregar pool de sugerencias en `data_service.py` (`_FOLLOWUP_POOLS`)
4. Si aplica gráfica, agregar mapeo en `chart_service.py` (`chart_for_intent()`)

### Modificar el System Prompt

1. Editar `SYSTEM_PROMPT` en `prompt_builder.py`
2. Incrementar `PROMPT_VERSION`
3. Las conversaciones nuevas usarán la nueva versión; las antiguas mantienen la suya

### Actualizar el Modelo de DeepSeek

Cambiar la variable de entorno `DEEPSEEK_MODEL`. Compatible con cualquier modelo de chat de OpenAI o DeepSeek.

### Agregar un Nuevo Tipo de Evento

1. Definir template en `event_templates.py`
2. Agregar lógica de detección en `event_engine.py` (`_run_checks_for_restaurant`)
3. Asignar prioridad y cooldown

---

## Pruebas

Para probar manualmente el flujo completo:

```bash
# 1. Iniciar servidor
python run.py

# 2. Hacer una consulta rápida (SQL)
curl -X POST http://localhost:5000/insights/api/conversations/draft \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..."  # Requiere auth

# 3. Enviar mensaje
curl -X POST http://localhost:5000/insights/api/conversations/1/messages \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{"content": "cuánto vendí ayer?"}'
```

Para probar el frontend, navegar a `http://localhost:5000/insights/`.

---

## Referencias

- [Prompt Builder](app/services/insights/prompt_builder.py) — System prompt y reglas
- [LLM Service](app/services/insights/llm_service.py) — Integración con DeepSeek
- [Context Manager](app/services/insights/context_manager.py) — Compresión de contexto
- [Event Engine](app/services/insights/event_engine.py) — Eventos automáticos
- [Frontend JS](app/static/js/insights.js) — Chat cliente
- [AGENTS.md](../AGENTS.md) — Guía rápida del proyecto
- [Env Vars Reference](GUIDE-06_Referencia_Env_Vars.md) — Variables de entorno

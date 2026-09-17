# Orderfox / Velzia — AI Agent Guide

**Stack:** Flask 3.x (Python) + Astro (menu público) + Vanilla JS + Tailwind CSS 4 + MariaDB (XAMPP, local) / MySQL 8 (CI, prod)
**Version:** v1.4.0

## Skills & MCP

### Skills Disponibles
| Skill | Prioridad | Para qué usarlo |
|-------|-----------|----------------|
| `frontend-design` | Alta | Diseño UI profesional (jerarquía, colores, tipografía, layouts) |
| `tailwind-css-patterns` | Alta | Patrones responsive con Tailwind CSS 4 |
| `accessibility` | Media | WCAG 2.2, screen reader, navegación teclado |
| `seo` | Media | Meta tags, structured data, sitemap, optimización búsqueda |
| `python-testing-patterns` | Alta | Patrones pytest, fixtures, mocking, TDD |

### MCP Configurados
| Servidor | Conexión | Uso |
|----------|----------|-----|
| `Conexion_MYSQL` | MariaDB local (XAMPP, :3306, root sin password) | Consultar DB, ver tablas, ejecutar queries |

> **⚠️ IMPORTANTE:** `Conexion_MYSQL` apunta al **MariaDB de XAMPP** local (puerto 3306, usuario `root` sin password, base `orderfox` — ver `DATABASE_URL` en `.env`). Si el MCP se ve rojo/inaccesible, encender **MySQL** desde el XAMPP Control Panel (Start → MySQL) y verificar que el puerto 3306 esté libre. No usar el contenedor Docker `orderfox-db` para la DB local.

**Regla:** Todo agente DEBE cargar los skills relevantes al iniciar su tarea usando el tool `skill`. Ningún agente debe trabajar sin sus skills cargados.

### Política de Skills (Ciclo de Vida)

1. **Transparencia:** Antes de cargar un skill, el agente DEBE explicar por qué lo necesita.
2. **Reutilización:** Si un skill se usará múltiples veces, dejarlo instalado.
3. **Desechables:** Si un skill se usa una sola vez, borrarlo al terminar.
4. **Justificación:** No cargar skills "por si acaso". Cada skill cargado debe tener un propósito claro.

## Quick Start

```bash
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # CI usa este, no requirements.txt
npm install
flask db upgrade                      # ejecutar siempre tras pull
npm run build:css                     # Tailwind 4 (sin tailwind.config.js)
python run.py                         # http://localhost:5000
```

Flask y Astro corren por separado. Astro (menú digital, `astro/`, puerto 4321) proxies `/menu/api` a Flask.

```bash
cd astro; npm run dev                 # Frontend Astro (menú público)
```

## Filosofía del Proyecto

- **Preferir simplicidad sobre complejidad.** Si hay dos soluciones igual de válidas, escoger la más simple.
- **No romper APIs existentes.** Los cambios deben ser backward-compatible. Depreciar, no eliminar.
- **Backend primero, frontend desacoplado.** La lógica de negocio vive en Flask; Astro es solo presentación.
- **Mobile First.** Todo el frontend debe funcionar y verse bien en móvil antes que en desktop.
- **No duplicar lógica.** Si un patrón aparece dos veces, extraerlo a un servicio o componente compartido.
- **No agregar dependencias sin justificación.** Cada librería nueva debe resolver un problema real, no una preferencia.
- **Las rutas no tienen lógica de negocio.** Flask routes solo orquestan: reciben request, llaman un service, devuelven response.
- **Archivos grandes son deuda técnica.** Si un archivo supera las ~400 líneas, el agente DEBE advertir al usuario automáticamente y proponer una factorización clara (extraer a services, helpers, o dividir en módulos). No esperar a que el usuario lo pida. Ejemplos concretos de lo que se debe evitar: routes con lógica inline de 300+ líneas, services que mezclan dominios distintos, models con 10+ clases en un solo archivo.
- **Límite pragmático:** Archivos de 400-700 líneas son aceptables si están bien organizados (una sola responsabilidad, lógica clara). Archivos de **800+ líneas** se consideran críticos y requieren factorización sí o sí antes de mergear.
- **⚠️ REGLA: Archivos de 500+ líneas — NO refactorizar automático.** Antes de modificar cualquier archivo o función que supere 500 líneas, el agente DEBE:
  1. **Identificar** el archivo y reportar cuántas líneas tiene.
  2. **Proponer** cómo dividirlo (extraer a módulos, separar responsabilidades, etc.).
  3. **Esperar confirmación** del usuario antes de ejecutar ningún cambio.
  4. **Ejecutar en etapas**, con tests verificados en cada paso antes de continuar.
  - Esto aplica tanto a archivos Python como JS. Nunca refactorizar "de pasada" durante otro cambio.

### Compromiso de Calidad (obligatorio)

El usuario no puede revisar cada cambio: el agente es 100% responsable de que nada se rompa en producción ni en desarrollo. Todo cambio DEBE cumplir:

- **Cero bugs escondidos.** Antes de dar una tarea por terminada: comprobar sintaxis de los archivos tocados (`py_compile`, `node --check`), y revisar manualmente los edge cases que los QA testers no cubren.
  - **Suite completa SOLO si se tocan archivos críticos:** correr la suite completa de pytest SOLO cuando el cambio toca archivos críticos del sistema (models, services, routes, utils, auth, init, settings, migrations). Si el cambio es solo frontend (JS, CSS, HTML, Astro) o docs/config, basta con `node --check`/build + verificar sintaxis. **No correr la suite completa "por si acaso".**
  - **Tests puntuales para cambios no críticos:** si se modifica un archivo JS/HTML/CSS específico, correr solo los tests que apliquen a ese archivo (si existen), no la suite completa.
- **No confiar ciegamente en pytest.** Un test en verde no es suficiente. Si una suite falla de forma intermitente, encontrar la causa raíz y arreglarla (ej. stubbear threads/hilos que pelean por recursos, mocks), nunca ignorarla ni asumir que "no volverá a pasar".
- **Los tests son tan importantes como el código.** Todo bug o regresión detectada se cubre con un test que lo reproduce antes de mergear.
- **Sin efectos colaterales.** Un cambio no debe alterar comportamiento no relacionado: backward-compatible, no romper APIs existentes, no tocar lógica ajena al ticket.
- **Verificación explícita.** Al terminar, reportar qué se validó (suite de tests, sintaxis, lint, corridas repetidas) para que el usuario vea la evidencia.
- **Pruebas reales cuando se pueda.** Si el cambio toca emails, integraciones o flujos externos, validar con un caso real (ej. script de prueba contra el servicio) además de los mocks.

## Arquitectura

Arquitectura basada en separación estricta de responsabilidades. No mover lógica entre capas.

```
Flask (app/)         → dashboard + auth + APIs REST
  app/routes/        → blueprints web (dashboard, auth, public)
  app/routes/api_*.py→ endpoints JSON (JWT o API key)
  app/services/      → lógica de negocio (insights, token, order, auth, category)
  app/services/insights/ → Copilot VZ (classifier, llm_service, prompt_builder, ...)
  app/utils/         → helpers (subscription, rate_limiter, auth)
  app/template/      → Jinja2 (dashboard, auth, common)
Astro (astro/)       → menú digital público (SSR, Tailwind v4)
```

### Entrypoints & Límites
- `run.py` → `app.create_app()` → registra blueprints, extensiones y APScheduler
- `settings.py` → carga todo de `.env`; no subir `.env` a git
- CSRF: exento en `/api/*` e `/insights/api/*` via `before_request` (flask-csrf)
- CORS: orígenes permitidos son localhost:3000/4321/5173 + SCANNER_IA_URL

## Comandos Clave

| Comando | Acción |
|---------|--------|
| `/build` | Build CSS (`npm run build:css`) |
| `/check` | Lint + tests + build CSS (todo pre-commit) |
| `/clean` | Limpia `__pycache__`, `*.pyc`, `.pytest_cache` |
| `/deploy` | Build CSS → `flask db upgrade` → inicia servidor |
| `/fix` | Ruff --fix + formatea código |
| `/health` | Verifica Flask, DB, Redis, ENV, IA |
| `/lint` | Ruff check del proyecto |
| `/logs` | Últimos errores del servidor |
| `/migrate` | Crea migración + upgrade |
| `/status` | Git branch + status + últimos commits |
| `/sync` | `git pull` → install deps → db upgrade → build CSS |
| `/test` | Tests con cobertura |
| `/stress` | `npm run stress:suite` — ejecuta suite completa de estrés (k6) |
| `/documentacion` | Documenta cambios recientes automáticamente |

## Delegación Automática

El agente principal PUEDE invocar sub-agentes automáticamente sin esperar instrucción del usuario cuando detecte que una tarea se beneficia de paralelización o expertise especializada.

### ¿Cuándo delegar?
- **Tareas con partes independientes** (ej. cambiar backend + frontend al mismo tiempo)
- **Expertise distinta** (ej. migrar DB + diseñar UI + escribir tests)
- **Tareas pesadas** que son más rápidas en paralelo que secuenciales
- **Investigación exploratoria** (ej. buscar patrones en múltiples directorios)

### ¿Cuándo NO delegar?
- Tareas triviales de 1-2 ediciones
- Cuando los sub-agentes no aportan valor (la comunicación suma overhead)
- Tareas estrictamente secuenciales donde una depende del resultado de otra

### Transparencia
Siempre informar al usuario cuando se esté delegando: *"Voy a lanzar X en paralelo para Y mientras yo hago Z"*.

Tests usan `sqlite:///:memory:` localmente. CI corre contra MySQL en contenedor.

## Security Audit

```bash
npm run audit:k6       # k6 headers + JWT audit
npm run audit:zap      # ZAP passive scan (requiere daemon activo)
npm run audit:zap-start  # Inicia ZAP daemon en segundo plano
npm run audit:zap-stop   # Detiene ZAP daemon
npm run audit:gitleaks   # Escaneo de secretos (SARIF -> tests/security/reports/gitleaks.sarif)
npm run audit:secrets    # Escaneo de secretos legible en consola
npm run audit:trivy      # Trivy: escaneo completo (Dockerfile + dependencias)
npm run audit:trivy:config # Trivy: solo Dockerfile/IaC misconfigs
npm run audit          # k6 + ZAP (full audit)
```

## Reglas de Negocio (No Triviales)

### Timezone
Todas las fechas en UTC. **Nunca** `datetime.now()` — siempre `datetime.now(timezone.utc)`.
Model usa `AwareDateTime` (strips timezone al guardar, lo restaura al leer).

### Suscripción
Única fuente de verdad: `get_subscription_status(restaurant)` en `app/utils/subscription.py`.
Estados: `trial` → `active` → `grace_period` → `expired`. Frontend recibe objeto precalculado.

### Tokens IA
Cada usuario tiene `AITokenWallet`. Primer análisis profundo de cada conversación consume 1 token. Consultas rápidas (SQL) y seguimientos no consumen. DeepSeek corre por cuenta de Velzia.

### Rate Limiting (pedidos)
Máx 3/min por IP. Ban 10 min si excede. Honeypot + mínimo 3s entre checkout y envío. `SERVICE_API_KEY` exime.

### Copilot VZ
- `insights.py`: blueprint con identidad propia, fuera del dashboard (`/insights/`)
- Clasificador híbrido: `quick` (SQL directo, gratis) vs `analysis` (DeepSeek, 1 token)
- **Modos de profundidad:** fast (7d, temp=0.2), normal (60d, temp=0.35), detailed (90d, temp=0.45) — configurable por usuario en Settings
- Compresión de contexto en 2 fases cuando el uso supera 80%/85% de los 12K tokens
- Prompt versionado (`PROMPT_VERSION` en `prompt_builder.py`) — cada conversación guarda su versión
- Las consultas de seguimiento (`analysis_active = True`) no descuentan crédito pero sí pagan DeepSeek
- **Web Search (Tavily):** consultas externas activadas por toggle del usuario. Fuentes se devuelven como `sources[]` en el response JSON, el frontend pinta tarjeta clickable. Los patrones de detección están en `web_search.py` (precios, tendencias, noticias). Los alimentos/commodities están en `_COMMON_NOUNS` del classifier para evitar falsos positivos.
- **Response format:** `{"success": true, "content": "...", "chart": ..., "sources": [{title, url, snippet}], "metadata": {...}, "thinking_steps": [...]}`
- **Thinking Panel:** pasos del sistema (clasificación, datos, web search, LLM) expandibles debajo de cada respuesta

### Menú Público
Redirige de Flask (`/menu/<slug>`) al frontend Astro (`ASTRO_BASE_URL/<slug>/`).
Si tocas el menú público, editas `astro/src/`, no `app/template/`.

## Convenciones

- **DB:** snake_case. **URLs:** kebab-case. **JS:** camelCase.
- **API responses:** `{"success": bool, "message": "...", "data": {...}}` o `{"error_code": "..."}`.
- **Web forms:** incluir `{{ csrf_token() }}`. API routes exentas.
- **Nuevo endpoint API:** crear blueprint en `app/routes/api_*.py` o extender existente.
- **Nuevo template:** `app/template/` (Flask) o `astro/src/pages/` (Astro).
- **CSS/JS separados:** Nunca escribir CSS ni JS dentro del HTML. Siempre crear archivos CSS y JS separados e importarlos.
- **Slugs reservados:** `api`, `admin`, `auth`, etc. — ver `RESERVED_SLUGS` en `app/routes/auth.py`.

## Gotchas

- Conexión local = **MariaDB XAMPP**: `mysql+pymysql://root:@localhost:3306/orderfox` (root sin password; encender **MySQL** en el XAMPP Control Panel). CI usa MySQL 8 en contenedor. Driver: `mysql+pymysql://user:pass@host/db`
- CSS: Tailwind 4 vía `@tailwindcss/cli`, no hay `tailwind.config.js`. Pre-build obligatorio en prod.
- `settings.APP_VERSION = '1.3.0'` está desactualizado (no sincronizado con tags de git)
- Rate limiter es in-memory (se pierde al reiniciar)
- Upload max 16MB a Cloudinary; `app/static/uploads/` es caché local (no auto-limpieza)
- Gmail requiere app-specific password, TLS por defecto
- APScheduler se inicia en `create_app()` — tareas: `scan_business_events` (hora), `manage_subscription_lifecycle` (3 AM, marca cuentas inactivas como `dormant` SIN borrar datos), `expire_pending_orders` (hora)
- **`Server` header**: Werkzeug/Flask dev server añade `Server: Werkzeug/...` después de `after_request`. Para suprimirlo se debe parchear `WSGIRequestHandler.server_version` y `sys_version` en `run.py` (no desde `app/__init__.py`).

### AI Package Hallucination Prevention
> **⚠️ REGLA DE ORO: Siempre verificar paquetes sugeridos por IA antes de instalar.**

Los LLMs alucinan nombres de paquetes que no existen. Atacantes publican paquetes maliciosos con esos nombres exactos. **Nunca instalar un paquete sin verificación humana.**

```bash
# REGLA: Antes de instalar cualquier paquete sugerido por IA:
pip index versions <nombre-del-paquete>
# Si NO aparece info del paquete → ES UNA ALUCINACIÓN, NO INSTALAR.
```

**Pasos obligatorios antes de `pip install`:**
1. Ejecutar `pip index versions <paquete>` — verificar que existe en PyPI
2. Verificar el publisher/repo — debe ser de una organización conocida (Pallets, Sentry, etc.)
3. Revisar `pip show <paquete>` — debe apuntar a un repo legítimo en GitHub
4. Solo entonces ejecutar `pip install <paquete>`

**Señales de alucinación:**
- Nombres de paquetes genéricos o "demasiado convenientes"
- Dependencias que resuelven problemas muy específicos con nombres sospechosos
- Paquetes sugeridos que no se encuentran en Google/pypi.org
- La IA sugiere `pip install` sin verificar primero que el paquete existe

**Protección adicional:**
- Usar `requirements.txt` con versiones fijas (ya se hace)
- Ejecutar `pip-audit` o `safety check` antes de cada deploy
- Todo PR que agregue dependencias nueva requiere aprobación

### AI Prompt Injection Protection
> **⚠️ REGLA DE ORO: Nunca confíes en datos de usuario que llegan al modelo de IA.**

Tu app usa DeepSeek en Copilot VZ. El mensaje del usuario viene directamente del frontend — un atacante puede enviar texto malicioso.

**Vectores de ataque en tu app:**
1. **Inyección directa**: Usuario envía "Ignore previous instructions" en el chat
2. **Manipulación de contexto**: Texto que imita instrucciones del sistema
3. **Fuga de información**: Intentar que la IA revele el system prompt o secrets

**Protección implementada (3 capas):**

| Capa | Archivo | Qué hace |
|------|---------|----------|
| **1. Sanitización** | `message_handler.py` | Detecta patrones de inyección y reemplaza por `[FILTRADO]` |
| **2. Límite** | `message_handler.py` | Máximo 2000 chars por mensaje |
| **3. Validación** | `llm_service.py` | Rechaza respuestas con contenido sospechoso |

**Reglas para agents:**
- **NUNCA** modificar `message_handler.py` para quitar la sanitización
- **NUNCA** pasar credenciales o secrets en el prompt del sistema
- **SIEMPRE** usar `validate_llm_response()` antes de mostrar respuesta al usuario
- **SIEMPRE** registrar intentos de inyección en logs para auditoría
- **LIMITAR** longitud de mensajes de usuario (max 2000 chars)

**Flujo seguro:**
```
Usuario → sanitize_user_message() → Clasificador → Prompt Builder → DeepSeek → validate_llm_response() → Usuario
            ↑ Filtra inyección                                    ↑ Rechaza si sospechoso
```

### Classifier: _COMMON_NOUNS
El classifier usa `_COMMON_NOUNS` para evitar falsos positivos en `is_foreign_restaurant_query()`. Si agregas una query que matchea `_WEAK_TRIGGER_RE` (de/del/de la + palabra), y esa palabra es un alimento o commodity (ej. "de pollo", "de arroz"), agrégala a `_COMMON_NOUNS` en `classifier.py`. Sin esto, "¿cuánto cuesta el pollo?" se bloquea como "restaurante ajeno".

## Stress Test (k6)

Suite ubicada en `tests/k6/`. Ejecutar:

```bash
npm run stress:suite                  # suite completa
npm run stress:runner                 # diagnóstico rápido
npm run stress:phase1                 # 5/10/20 usuarios
```

A 30 VUs el Flask dev server muestra degradación. **En producción usar gunicorn con ≥4 workers.**
k6 v2.1.0 en `C:\PROGRA~1\k6\k6.exe` (short name para npm scripts sin espacios).

## CSRF

Flask-WTF 1.2.2 no respeta `request._csrf_exempt`. Para exentar rutas `/api/` e `/insights/api/` se usa `WTF_CSRF_CHECK_DEFAULT = False` + `before_request` manual en `app/__init__.py:57-71`. No añadir `@csrf.exempt` por endpoint.

## Enlaces Rápidos

- [docs/02-GUIDES/GUIDE-07_Copilot_VZ.md](docs/02-GUIDES/GUIDE-07_Copilot_VZ.md) — documentación completa de Copilot VZ
- [docs/02-GUIDES/GUIDE-09_Better_Stack.md](docs/02-GUIDES/GUIDE-09_Better_Stack.md) — integración Better Stack Error Tracking
- [settings.py](settings.py) — todas las variables de entorno
- [.env.example](.env.example) — plantilla de configuración

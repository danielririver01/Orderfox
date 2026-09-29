# 01 — Inventario técnico (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

Leyenda de clasificación: ver [README.md](README.md#2-cómo-leer-estos-documentos--clasificación-de-cada-hallazgo).

---

## 1. Qué es el producto

`[CÓDIGO]` Plataforma SaaS multi-inquilino de gestión de pedidos para restaurantes
en Colombia. Cada restaurante (`restaurants`) tiene su menú digital público,
recibe pedidos por QR, y su dueño administra todo desde un panel Flask.
Evidencia: `README.md`, `app/models/core.py:40` (`Restaurant`), `app/utils/subscription.py:5` (`PLAN_LIMITS`).

`[CÓDIGO]` El aislamiento entre inquilinos es **por columna** `restaurant_id`, no
por esquema ni por base de datos. Evidencia: 21 de las 27 tablas llevan
`restaurant_id` o cuelgan de una que lo lleva (ver [03-modelo-de-datos.md](03-modelo-de-datos.md)).

---

## 2. Estructura de carpetas

```
Orderfox/
├── app/                    Aplicación Flask (backend + dashboard + APIs)
│   ├── __init__.py         Application factory  (465 líneas)
│   ├── models/             8 archivos  ·   904 líneas  — SQLAlchemy por dominio
│   ├── routes/             25 archivos · 7.438 líneas  — blueprints web + API
│   ├── services/           39 archivos · 10.521 líneas — lógica de negocio
│   │   └── insights/       14 archivos               — Copilot VZ (IA)
│   ├── utils/              11 archivos · 1.354 líneas — helpers transversales
│   ├── forms/              3 archivos  ·    80 líneas — WTForms
│   ├── schemas/            (paquete prácticamente vacío)
│   ├── template/           77 plantillas Jinja2   ← carpeta REAL de plantillas
│   ├── templates/          1 archivo huérfano     ← NO la usa Flask
│   ├── static/js/          39 archivos · 9.403 líneas de JS vanilla
│   └── static/CSS/         20 archivos CSS
├── astro/                  Frontend público (menú digital + landing)
│   └── src/                29 archivos .astro + 5 .ts
├── migrations/             Alembic · 31 migraciones + carpeta backup/ (3)
├── tests/                  24 tests pytest + k6 + auditoría de seguridad
├── deploy/                 nginx, systemd, scripts de servidor
├── docs/                   Documentación previa (28 archivos)
├── knowledge_base/         5 .md — base de conocimiento de negocio para el LLM
├── .github/workflows/      1 workflow: ci.yml
├── run.py                  Entrypoint web
├── run_scheduler.py        Entrypoint solo-tareas
├── settings.py             Configuración única (lee .env)
└── docker-compose.yml      Orquestación (3 servicios)
```

`[EJECUTADO]` Conteos obtenidos con `find` y `wc -l` sobre el checkout limpio.

---

## 3. Puntos de entrada

| Entrypoint | Qué hace | Evidencia |
|---|---|---|
| `run.py` | Crea la app y la sirve en `0.0.0.0:5000`. **Parchea `WSGIRequestHandler.server_version`** para ocultar la cabecera `Server`. | `run.py:1-12` |
| `run_scheduler.py` | Crea la app y duerme en bucle: proceso dedicado **solo** a las tareas de APScheduler. | `run_scheduler.py:1-12` |
| `app.create_app()` | *Application factory*: extensiones, CSRF, CORS, ProxyFix, WhiteNoise, **scheduler**, 25 blueprints, manejadores de error. | `app/__init__.py:27-465` |
| `gunicorn ... run:app` | Entrypoint de producción y de Docker. | `Dockerfile:41`, `start.sh:7`, `docker-compose.yml:19` |
| `flask cleanup-accounts` | Comando CLI que ejecuta el ciclo de vida de suscripciones a mano. | `app/__init__.py:392-398` |
| `astro dev` / `astro build` | Frontend público, puerto 4321. | `astro/package.json`, `astro/astro.config.mjs` |

`[CÓDIGO]` **`run.py` no es equivalente a `gunicorn run:app`.** El parche que
suprime la cabecera `Server` vive en `run.py:2-4`, *antes* de importar la app.
Cualquier arranque que no pase por `run.py` no aplica ese parche.
`[EJECUTADO]` Arrancando la app sin `run.py`, la respuesta incluyó
`Server: Werkzeug/3.1.7 Python/3.11.2`.

---

## 4. Módulos y responsabilidades

### 4.1 Modelos (`app/models/`) — 27 tablas en 6 dominios

| Archivo | Clases | Dominio |
|---|---|---|
| `core.py` | `AwareDateTime`, `Restaurant`, `User`, `Category`, `Product`, `Modifier`, `Table` | Núcleo y catálogo |
| `orders.py` | `Order`, `OrderItem`, `OrderEvent`, `OrderCounter` | Pedidos y trazabilidad |
| `cash.py` | `CashRegister` | Cierres de caja |
| `ai.py` | `CopilotConversation`, `CopilotMessage`, `CopilotBusinessEvent`, `AILlmCall`, `PlatformBenchmark` | Copilot VZ |
| `tokens.py` | `AITokenWallet`, `AITokenTransaction` | Créditos de IA |
| `rewards.py` | `PreRegistration`, `TrialHistory`, `Expense`, `RewardClaim`, `UserAchievement`, `Streak`, `DiscountCoupon` | Recompensas y captación |
| `reservations.py` | `Reservation`, `ReservationSettings` | Reservas de mesa |

### 4.2 Rutas (`app/routes/`) — 25 blueprints

`[EJECUTADO]` Mapa extraído de `app.url_map` en ejecución: **200 reglas**, **25 blueprints**.

**Blueprints web (sesión Flask + CSRF):**

| Blueprint | Prefijo | Rutas | Responsabilidad |
|---|---|---|---|
| `auth` | *(raíz)* | 19 | Login, Clerk sync, planes, pago, webhook legacy, legal |
| `dashboard` | `/dashboard` | 21 | Panel, estadísticas, perfil, QR, suscripción, logros |
| `products` | `/products` | 13 | CRUD de productos y modificadores |
| `orders` | `/orders` | 11 | Gestión de pedidos del restaurante |
| `categories` | `/categories` | 8 | CRUD de categorías |
| `tables` | `/dashboard/tables` | 6 | Mesas y sus QR |
| `employees` | `/dashboard` | 6 | Alta/baja de empleados (solo `owner`) |
| `employee_portal` | `/empleado` | 8 | Portal con PIN para cajero/mesero |
| `reservations` | `/dashboard/reservations` | 3 | Panel de reservas |
| `cash_register` | `/cash-register` | 10 | Centro de caja + su propio copiloto |
| `insights` | `/insights` | 15 | Copilot VZ (identidad propia, fuera del dashboard) |
| `rewards` | `/reclamar` | 3 | Reclamo público de recompensas |
| `public` | *(raíz)* | 7 | Menú público y APIs `/menu/api/*` |

**Blueprints API (JSON, exentos de CSRF):**

| Blueprint | Prefijo | Rutas |
|---|---|---|
| `api_auth` | `/api/auth` | 6 |
| `api_dashboard` | `/api/dashboard` | 9 |
| `api_products` | `/api/products` | 10 |
| `api_orders` | `/api/orders` | 8 |
| `api_reservations` | `/api/reservations` | 9 |
| `api_categories` | `/api/categories` | 7 |
| `api_tables` | `/api/tables` | 4 |
| `api_webhooks` | `/api/v1/webhooks` | 4 |
| `api_public` | `/api/public` | 3 |
| `tokens` | *(raíz)* | 4 (`/api/tokens/*`) |
| `api_docs` | `/api/docs` | 2 (Swagger UI + spec) |
| `api_email` | `/api/email` | 1 |

### 4.3 Servicios (`app/services/`) — la lógica de negocio

| Servicio | Responsabilidad |
|---|---|
| `order_service.py` (622) | Creación idempotente de pedidos, numeración atómica, transiciones de estado, pagos, trazabilidad |
| `dashboard_service.py` (625) | Métricas, estadísticas y agregados del panel |
| `auth_service.py` (542) | Sincronización con Clerk, alta de restaurante, borrado de cuenta |
| `public_menu_service.py` (509) | Armado del menú público y validación de pedidos habilitados |
| `reservation_service.py` (462) | Disponibilidad, creación y ciclo de vida de reservas |
| `auto_photo_service.py` (481) | Fotos automáticas de productos (Unsplash / Gemini / biblioteca local) |
| `subscription_service.py` (350) | Pagos Mercado Pago y renovación de planes |
| `cash_register_service.py` (361) | Cierres de caja sin solapamiento |
| `employee_service.py` (291) | Empleados, PIN, bloqueo por fuerza bruta |
| `token_service.py` (241) | Billetera de créditos IA con bloqueo pesimista |
| `reward_service.py`, `streak_service.py`, `achievement_engine.py` | Gamificación |
| `notification_service.py` | Notificaciones push vía ntfy.sh |
| `mail_service.py`, `reminder_service.py` | Correo SMTP (Gmail) y recordatorios |
| `qr_service.py`, `theme_service.py`, `category_service.py`, `product_service.py`, `table_service.py` | Apoyo por dominio |

**Subpaquete `services/insights/` — Copilot VZ (IA):**

`classifier.py` (clasificación rápida/análisis) · `data_service.py` (931 líneas, el
archivo más grande del proyecto) · `llm_service.py` (DeepSeek) · `prompt_builder.py`
(prompt versionado) · `message_handler.py` (517, sanitización anti-inyección) ·
`context_manager.py` (compresión de contexto) · `web_search.py` (Tavily) ·
`benchmark_service.py` (medianas anónimas con k-anonymity) · `event_engine.py` +
`event_templates.py` (eventos de negocio) · `chart_service.py` ·
`conversation_service.py` · `knowledge_selector.py` · `helpers.py`.

### 4.4 Utilidades (`app/utils/`)

| Archivo | Responsabilidad |
|---|---|
| `subscription.py` (530) | **Fuente única de verdad de planes, límites y estado de suscripción** |
| `auth.py` (237) | Decoradores `require_auth`, `require_active`, `require_feature`, `require_role` |
| `rate_limiter.py` | Anti-bots de pedidos y reservas (3/min por IP, ban 10 min) |
| `timezone.py` | UTC ↔ Colombia (UTC-5 fijo, sin horario de verano) |
| `restaurant.py` | Resolución del restaurante actual desde la sesión |
| `jwt_auth.py` | Resolución de usuario/restaurante desde JWT |
| `mp_webhook.py` | Verificación HMAC-SHA256 de webhooks de Mercado Pago |
| `image_handler.py` | Subida a Cloudinary |
| `cover_bank.py`, `latam_photo_library.py` | Imágenes por tipo de cocina |
| `constants.py` | `RESERVED_SLUGS` (20 slugs reservados) |

---

## 5. Dependencias externas

### 5.1 Python — `requirements.txt` (60 paquetes, todos con versión fija)

`[CÓDIGO]` Todas las versiones están fijadas con `==`. No hay rangos.

| Categoría | Paquetes principales |
|---|---|
| Framework | `Flask==3.1.3`, `Werkzeug==3.1.7`, `Jinja2==3.1.6` |
| Extensiones Flask | `Flask-SQLAlchemy 3.1.1`, `Flask-Migrate 4.1.0`, `Flask-WTF 1.2.2`, `Flask-JWT-Extended 4.7.1`, `Flask-Limiter 4.1.1`, `Flask-Mail 0.10.0`, `Flask-APScheduler 1.13.1`, `flask-cors 6.0.2` |
| ORM / migraciones | `SQLAlchemy==2.0.48`, `alembic==1.18.4` |
| **Drivers de BD** | `PyMySQL==1.1.2` **y** `psycopg2-binary==2.9.10` — *ambos instalados* |
| Servidor | `gunicorn==25.2.0`, `whitenoise==6.12.0` |
| Pagos | `mercadopago==2.3.0` |
| Autenticación | `Authlib`, `PyJWT`, `svix` (verificación de webhooks Clerk) |
| Imágenes | `cloudinary==1.44.2`, `pillow==12.3.0`, `qrcode==8.2` |
| IA | `tavily-python==0.5.1` (DeepSeek se consume por HTTP directo, sin SDK) |
| Observabilidad | `sentry-sdk==2.28.0` |
| Documentación API | `apispec[marshmallow]==6.10.0`, `marshmallow==4.3.0` |

`[CÓDIGO]` `requirements-dev.txt` añade `pytest 9.0.3`, `pytest-flask`,
`pytest-cov 6.1.1`, `flake8 7.2.0`, `bandit 1.9.4` y
`pip-audit 2.10.1`.

`[CONTRADICCIÓN]` Se instalan los dos drivers de base de datos a la vez
(`PyMySQL` y `psycopg2-binary`) porque el repositorio no tiene un único motor
decidido — ver [06-riesgos-y-deuda-tecnica.md](06-riesgos-y-deuda-tecnica.md#c-01).

### 5.2 Node — raíz y `astro/`

| Archivo | Dependencias |
|---|---|
| `package.json` (raíz) | Solo `@tailwindcss/cli ^4.2.4` y `tailwindcss ^4.2.4`. Su único fin es compilar el CSS del dashboard. |
| `astro/package.json` | `astro ^7.0.7`, `@astrojs/vercel ^11.0.0`, `@tailwindcss/vite ^4.3.2`, `tailwindcss ^4.3.2`, `typescript ^7.0.2` (dev) |

`[CÓDIGO]` No hay `tailwind.config.js`: Tailwind 4 se configura desde el CSS.

`[CÓDIGO]` **Los dos proyectos Node son independientes** y fijan versiones
distintas de Tailwind (4.2.4 en la raíz, 4.3.2 en Astro).

### 5.3 Servicios de terceros

| Servicio | Para qué | Variables | Verificado |
|---|---|---|---|
| **Clerk** | Autenticación de dueños | `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_JWT_ISSUER`, `CLERK_WEBHOOK_SECRET` | ❌ requiere credenciales |
| **Mercado Pago** | Cobro de suscripciones y recargas | `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY`, `MP_WEBHOOK_SECRET` | ❌ |
| **Cloudinary** | Alojamiento de imágenes | `CLOUDINARY_*` | ❌ |
| **DeepSeek** | LLM del Copilot VZ | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_URL`, `DEEPSEEK_MODEL` | ❌ |
| **Tavily** | Búsqueda web del Copilot | `TAVILY_API_KEY`, `TAVILY_MONTHLY_LIMIT` | ❌ |
| **ntfy.sh** | Notificación de pedido nuevo | `Restaurant.ntfy_topic` (en BD, no en `.env`) | ❌ |
| **Gmail SMTP** | Correos transaccionales | `MAIL_*` | ❌ |
| **Unsplash + Gemini** | Fotos automáticas de productos | `UNSPLASH_ACCESS_KEY`, `GEMINI_API_KEY`, `AUTOPHOTO_ENABLED` | ❌ |
| **Sentry / Better Stack** | Seguimiento de errores | `SENTRY_DSN` (opcional) | ❌ |
| **Scanner IA** | Escaneo de facturas | `SCANNER_IA_URL`, `SERVICE_API_KEY` | ❌ **repo externo** |

`[CÓDIGO]` **El Scanner IA (`Receipt-Scanner-AI`) no está en este repositorio.**
`docker-compose.yml:37` lo construye desde `../Receipt-Scanner-AI`, una ruta
hermana que no existe en el checkout. Comparte la **misma base de datos**
(`DATABASE_URL`) — ver la evidencia de tablas `velzia_*` en
[03-modelo-de-datos.md](03-modelo-de-datos.md#5-tablas-que-no-pertenecen-a-esta-aplicación).

---

## 6. Archivos de configuración

| Archivo | Rol |
|---|---|
| `settings.py` | **Única clase `Config`**. Lee todo de `.env` vía `python-dotenv`. Falla al arrancar si falta `SECRET_KEY` (`settings.py:14-18`). |
| `.env.example` | Plantilla con 40+ variables documentadas. |
| `pytest.ini` | `testpaths=tests`, cobertura obligatoria **≥ 35 %**. |
| `gunicorn_config.py` | Config de producción: `bind 127.0.0.1:8000`, `workers = CPU*2+1`, logs en `/var/log/orderfox/`. |
| `docker-compose.yml` / `.override.yml` | 3 servicios: `orderfox`, `orderfox-scheduler`, `receipt-scanner`. |
| `Dockerfile` / `Dockerfile.dev` | Producción multi-etapa (python:3.12-slim + node:20-alpine) / desarrollo. |
| `.gitleaks.toml` | Reglas de detección de secretos. |
| `alembic.ini`, `migrations/env.py` | Migraciones. |
| `AGENTS.md` | Guía de convenciones para agentes de IA y desarrolladores (18 KB). |
| `opencode.json`, `.opencode/agents/`, `skills-lock.json` | Configuración de herramientas de IA del equipo. |

`[CÓDIGO]` **No existe separación de entornos por clase de configuración.** Hay
una sola `Config`; el comportamiento cambia solo por variables de entorno
(`FLASK_DEBUG`, `SENTRY_DSN`, …). `app/__init__.py` no lee `FLASK_ENV` para
elegir configuración, aunque sí lo usa como etiqueta de Sentry
(`app/__init__.py:99`).

`[CÓDIGO]` `gunicorn_config.py` existe pero **ningún entrypoint lo usa**:
`Dockerfile:41`, `start.sh:7` y `docker-compose.yml:19` pasan los parámetros por
línea de comandos (`--workers 3`) en vez de `-c gunicorn_config.py`. Los valores
difieren: 3 workers fijos frente a `CPU*2+1`, y puerto `5000` frente a `8000`.

---

## 7. Base de datos, migraciones y scripts

| Elemento | Estado |
|---|---|
| Migraciones Alembic | **31** en `migrations/versions/` |
| Cabeza (head) | `c0a5f7e8d9b1` — `[EJECUTADO]` `flask db heads` devuelve **una sola cabeza**, sin ramas divergentes |
| Migración base | `baf135af1685_fresh_start.py` |
| Carpeta `migrations/versions/backup/` | 3 archivos fuera de la cadena de Alembic |
| SQL suelto | `migrations/raw_add_business_events.sql`, `migrations/supabase_schema.sql` |
| Parches manuales | `deploy/9b0c1d2e3f4a_fix.py`, `deploy/a4b2c3d4e5f6_fix.py`, `deploy/e4b30b77e164_fix.py` |

`[EJECUTADO]` `flask db upgrade` aplica las 31 migraciones **sin errores** sobre
una base SQLite vacía.

`[CÓDIGO]` `migrations/supabase_schema.sql` sugiere que en algún momento se usó
Supabase (PostgreSQL). No hay ninguna referencia a Supabase en `app/` ni en
`settings.py`. `[INFERIDO]` es un residuo histórico. `[PENDIENTE]` confirmar.

**Scripts sueltos en la raíz:**

| Script | Qué hace | Observación |
|---|---|---|
| `seed_demo_data.py` | Siembra datos de demostración | Uso legítimo |
| `scripts/reset_felicia_demo.py` | Reinicia un restaurante de demo concreto | Específico de un cliente |
| `rescues_db.py` | **Ejecuta `DROP TABLE` sobre `ai_token_*` con `FOREIGN_KEY_CHECKS = 0`** | ⚠️ Destructivo, sin confirmación ni salvaguarda. Sintaxis solo-MySQL |
| `test_db.py` | Imprime todos los usuarios de la BD | Script de depuración, no es un test de pytest |
| `test_pg_connection.py` | Prueba conexión a PostgreSQL | Script de depuración |

`[CÓDIGO]` `test_db.py` y `test_pg_connection.py` empiezan por `test_` pero
**no los recoge pytest** porque `pytest.ini` fija `testpaths = tests`. Aun así
confunden: parecen pruebas y no lo son.

---

## 8. APIs e integraciones

`[EJECUTADO]` **200 rutas** en total. De ellas, **~65 son endpoints JSON**.

| Superficie | Autenticación | Evidencia |
|---|---|---|
| `/api/*` (excepto `/api/public/*`) | JWT `Bearer` **o** sesión Flask, vía `require_auth` | `app/utils/auth.py:12-46` |
| `/insights/api/*` | Igual que arriba | `app/routes/insights.py` |
| `/menu/api/*` | **Pública**, protegida por honeypot + rate limit por IP | `app/routes/public.py:20-140` |
| `/api/public/*` | **Pública** (lectura del menú) | `app/routes/api_public.py` |
| `/api/v1/webhooks/*` | Firma HMAC (Mercado Pago) / Svix (Clerk) / `SERVICE_API_KEY` | `app/routes/api_webhooks.py`, `app/utils/mp_webhook.py` |
| `/webhook` | Webhook **legacy** de Mercado Pago, firma HMAC propia | `app/routes/auth.py:508-557` |
| `/reclamar/*` | Pública, por `short_code`/token | `app/routes/rewards.py` |

### Documentación OpenAPI — incompleta y con errores

`[EJECUTADO]` `GET /api/docs/spec.json` devuelve una especificación OpenAPI 3.0.3
con **15 rutas documentadas de ~65 endpoints JSON reales (≈23 %)**.

`[EJECUTADO]` Dos de esas 15 rutas **no existen**: se les hizo `POST` real y
devolvieron **404**.

| Ruta en la spec | Respuesta real | Ruta real equivalente |
|---|---|---|
| `POST /api/auth/sync-clerk` | **404** | `POST /api/sync-clerk` |
| `POST /api/orders/create` | **404** | `POST /api/orders` |

`[EJECUTADO]` El título de la spec dice `Orderfox API 1.3.0`
(`app/routes/api_docs.py:31`) mientras `settings.APP_VERSION = '1.4.0'`.

---

## 9. Pruebas existentes

### 9.1 pytest — la suite real

`[EJECUTADO]` Suite completa con las variables de entorno que usa el CI:

```
620 passed, 2 failed, 1060 warnings in 63.52s
Cobertura total: 58.38 %  (umbral exigido: 35 %)
```

| Archivo | Tema |
|---|---|
| `test_account_deletion.py` (43) | Borrado de cuenta y cancelación diferida |
| `test_reservations*.py` (3 archivos) | Reservas: servicio, panel y público |
| `test_cash_register*.py` (2) | Centro de caja y su copiloto |
| `test_order_idempotency.py`, `test_order_traceability.py` | Pedidos |
| `test_race_conditions.py` | Concurrencia |
| `test_subscription.py` | Suscripciones |
| `test_employees.py` | Roles y PIN |
| `test_payment.py` | Mercado Pago |
| `test_copilot_follow_up_cap.py` | Tope de seguimientos del Copilot |
| `test_auto_photo.py`, `test_image_*.py` | Imágenes |
| `test_public_menu.py`, `test_models.py`, `test_services.py`, `test_rate_limiter.py`, `test_theme_service.py`, `test_benchmarks_knowledge.py`, `test_business_event_consume.py`, `test_auth_setup_terms.py` | Resto |

`[CÓDIGO]` `tests/conftest.py:6` fuerza `DATABASE_URL = sqlite:///:memory:`, así
que **la suite nunca se ejecuta contra el motor de producción**.

### 9.2 Otras pruebas (no ejecutadas aquí)

| Tipo | Ubicación | Estado |
|---|---|---|
| Carga (k6) | `tests/k6/` — 8 escenarios | `[CÓDIGO]` `package.json` apunta a `C:\PROGRA~1\k6\k6.exe`: **solo Windows** |
| Seguridad (ZAP, Trivy, gitleaks) | `tests/security/` | `[CÓDIGO]` orquestado con `.ps1`: **solo Windows** |
| Frontend (Jest/Vitest) | `tests/frontend/*.test.js`, `tests/example.spec.js` | `[CÓDIGO]` `npm test` devuelve `Error: no test specified && exit 1`. **No hay runner configurado: no se ejecutan nunca** |

---

## 10. CI/CD y despliegue

`[CÓDIGO]` Un solo workflow: `.github/workflows/ci.yml`, disparado en `push` y
`pull_request` contra `main`. La descripción de los pasos 1–7 conserva el
snapshot del commit de referencia; el workflow vigente ya no excluye
`TestLLMCallTelemetry`.

**Job `test`:**
1. `postgres:14` como servicio — `DATABASE_URL: postgresql://...`
2. Python **3.12** + Node **20**
3. `pip install psycopg2-binary` + `pip install -r requirements-dev.txt`
4. `npm ci` → `npm run build:css`
5. `flask db upgrade`
6. `flake8 app/ --max-line-length=120 **--exit-zero**`
7. En el commit de referencia: `pytest --tb=short -q --no-header **-k "not TestLLMCallTelemetry"**`
   **Estado vigente:** `pytest --tb=short -q --no-header` (sin exclusión).

**Job `deploy`:** solo en `push` a `main`; SSH a Oracle Cloud y ejecuta
`deploy/update_server.sh`.

`[CÓDIGO]` Dos decisiones del CI que conviene conocer:
- **`--exit-zero` en flake8**: el lint *nunca* rompe la construcción. Los 5
  errores `F821` (nombre indefinido) documentados en
  [06-riesgos-y-deuda-tecnica.md](06-riesgos-y-deuda-tecnica.md) pasan
  desapercibidos.
- **`-k "not TestLLMCallTelemetry"`**: fue una exclusión del commit de
  referencia. El workflow vigente no usa ese filtro; los tests se mantienen en
  la suite mediante mocks deterministas.

`[CÓDIGO]` El CI vigente ejecuta `pip-audit --strict` como puerta bloqueante y
Bandit como chequeo informativo. La suite de seguridad externa no forma parte
de este workflow.

**Artefactos de despliegue:** `deploy/nginx/orderfox.conf` y `orderfox_ssl.conf`,
`deploy/systemd/orderfox.service`, `deploy/setup_server.sh`,
`deploy/update_server.sh`, `deploy/backup_pg.sh` (nombre: PostgreSQL),
`deploy/setup_pg.sql`, `deploy/pg_listen.conf`, `deploy/debug_502.sh`.

---

## 11. Código abandonado, duplicado o sin uso aparente

### 11.1 Confirmado sin uso

| Elemento | Evidencia |
|---|---|
| `app/templates/public/subscription_expired.html` | `[CÓDIGO]` Flask usa `template_folder='template'` (`app/__init__.py:29`), **no `templates`**. `[EJECUTADO]` `grep -rn "subscription_expired"` en todo el repo: **0 coincidencias**. Inalcanzable. |
| `gunicorn_config.py` | Ningún entrypoint lo referencia (ver §6). |
| `test_flask_output.txt` | Archivo de 0 bytes versionado. |
| `test_flask_errors.txt` | 73 bytes de salida de depuración versionada. |
| `test_qr_blur.png`, `test_qr_sin_label.png`, `test_qr_terraza.png` | Capturas de prueba (43 KB) en la raíz. |
| `menu_check.json` | 18 KB de volcado de diagnóstico en la raíz. |

### 11.2 Plantillas Jinja2 sin referencia detectada

`[INFERIDO]` — pueden cargarse dinámicamente; verificar antes de borrar.

`auth/clerk_handshake.html` · `auth/privacy.html` · `auth/terms.html` ·
`components/product_macros.html` · `email/change_email.html` · `errors/400.html`

`[CÓDIGO]` `auth/privacy.html` y `auth/terms.html` son coherentes con lo
observado: `[EJECUTADO]` `GET /privacy` y `GET /terms` devuelven **302 → `/legal`**,
así que esas dos plantillas ya no se renderizan.

### 11.3 Duplicación funcional

| Duplicado | Detalle |
|---|---|
| **Dos webhooks de Mercado Pago** | `POST /webhook` (`app/routes/auth.py:508`, IPN legacy) y `POST /api/v1/webhooks/mercadopago` (`app/routes/api_webhooks.py:136`, Webhooks API). El propio código llama al primero *legacy*. |
| **Dos rutas de cancelación de cuenta** | `POST /dashboard/cancel-account` (web, funciona) y `POST /api/dashboard/cancel-account` (API, **rota** — ver [R-02](06-riesgos-y-deuda-tecnica.md#r-02)). |
| **Dos copilotos de IA** | `app/routes/insights.py` (Copilot VZ) y `app/services/cash_register_copilot.py` (copiloto de caja), ambos sobre `CopilotConversation` diferenciados por `source`. |
| **Modificadores en dos superficies** | `/products/<id>/api/modifiers` y `/api/products/<id>/modifiers`. |
| **`app/template/` vs `app/templates/`** | Dos carpetas con un carácter de diferencia; solo la primera es real. |
| **Dos proyectos Tailwind** | Raíz (4.2.4) y `astro/` (4.3.2). |

### 11.4 Residuos y material no productivo versionado

| Elemento | Tamaño / contenido |
|---|---|
| `video_presentation/` | `index.html`, `DESIGN.md` y 5 `.meta.json` de renders de abril 2026 |
| `backups/felicia_reset_2026-09-03/snapshot.json` | Copia puntual de datos de un cliente |
| `migrations/versions/backup/` | 3 migraciones fuera de la cadena |
| `.playwright-mcp/` | Carpeta de artefactos de herramienta |
| `memories/repo/` | 2 `.md` de contexto para agentes de IA |
| `deploy/*_fix.py` | 3 parches manuales de migraciones aplicados en servidor |

`[PENDIENTE]` Ninguno de estos elementos parece necesario para ejecutar el
sistema, pero conviene confirmarlo antes de eliminarlos — ver
[07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-05).

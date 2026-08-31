# Guía de Arquitectura del Código Base — Orderfox / Velzia

**Versión:** 2.0 | **Fecha:** 2026-08-22 | **Versión del Proyecto:** 1.4.0 (settings.APP_VERSION) / tag git `v1.4.1`
> ⚠️ `settings.APP_VERSION='1.4.0'` está desincronizado del último tag git (`v1.4.1`). No usar como fuente de verdad.

---

## 1. Estructura General del Proyecto

```
Orderfox/
├── app/                          # Paquete principal Flask (backend)
│   ├── __init__.py               # App factory (create_app) + extensiones + APScheduler + CLI
│   ├── models/                   # Modelos SQLAlchemy (paquete, ya NO es app/models.py)
│   │   ├── core.py               # Restaurant, User, Category, Product, Modifier, Table
│   │   ├── orders.py             # Order, OrderItem, OrderEvent, OrderCounter
│   │   ├── rewards.py            # PreRegistration, TrialHistory, Expense, RewardClaim,
│   │   │                         #   UserAchievement, Streak, DiscountCoupon
│   │   ├── ai.py                 # CopilotConversation, CopilotMessage, CopilotBusinessEvent, AILlmCall
│   │   ├── cash.py               # CashRegister
│   │   └── tokens.py             # AITokenWallet, AITokenTransaction
│   ├── extensions.py             # Inicialización de Flask extensions
│   ├── extensions... (csrf.py, tasks.py)
│   ├── routes/                   # Blueprints (~22 módulos)
│   │   ├── auth.py               # Autenticación web + Clerk
│   │   ├── dashboard.py          # Dashboard web del dueño
│   │   ├── categories.py         # CRUD categorías (web)
│   │   ├── products.py           # CRUD productos (web)
│   │   ├── orders.py             # Gestión de pedidos (web)
│   │   ├── tables.py             # Gestión de mesas (web)
│   │   ├── public.py             # Ruta pública de pedidos (cliente)
│   │   ├── cash_register.py      # Caja registradora (web)
│   │   ├── employees.py          # Gestión de empleados/roles/PIN
│   │   ├── rewards.py            # Recompensas/fidelización
│   │   ├── tokens.py             # Gestión de tokens AI (web)
│   │   ├── insights.py           # Copilot VZ (Estratégico) — blueprint propio /insights/
│   │   ├── api_auth.py           # API autenticación
│   │   ├── api_dashboard.py      # API dashboard
│   │   ├── api_categories.py     # API products/categories
│   │   ├── api_products.py
│   │   ├── api_orders.py
│   │   ├── api_tables.py
│   │   ├── api_public.py         # API pública (pedidos cliente)
│   │   ├── api_email.py
│   │   ├── api_docs.py
│   │   └── api_webhooks.py       # Webhooks (Mercado Pago, etc.)
│   ├── services/                 # Lógica de negocio (capa gruesa)
│   │   ├── auth_service.py       # Registro, login, Clerk sync
│   │   ├── order_service.py      # CRUD pedidos + validación cantidad
│   │   ├── product_service.py / category_service.py / table_service.py
│   │   ├── cash_register_service.py / cash_register_copilot.py  # Caja + Copilot de Caja
│   │   ├── dashboard_service.py  # Estadísticas
│   │   ├── public_menu_service.py
│   │   ├── token_service.py      # Wallet de tokens AI (PyJWT, NO python-jose)
│   │   ├── subscription_service.py  # Reactivación, planes
│   │   ├── employee_service.py
│   │   ├── mail_service.py / notification_service.py / reminder_service.py
│   │   ├── qr_service.py / theme_service.py
│   │   ├── reward_service.py / streak_service.py / achievement_engine.py / achievement_definitions.py
│   │   └── insights/             # Copilot VZ (paquete)
│   │       ├── classifier.py     # quick (SQL) vs analysis (DeepSeek)
│   │       ├── llm_service.py    # Llamada a DeepSeek + validate_llm_response
│   │       ├── prompt_builder.py # SYSTEM_PROMPT v1.3 (estratega)
│   │       ├── message_handler.py# Sanitización anti-inyección (NO quitar)
│   │       ├── context_manager.py# Compresión 2 fases (80%/85%)
│   │       ├── conversation_service.py / data_service.py / chart_service.py
│   │       ├── event_engine.py / event_templates.py / helpers.py
│   ├── utils/
│   │   ├── auth.py               # Decoradores UNIFICADOS (require_auth, require_active,
│   │   │                         #   require_feature, require_role) — reemplazan a jwt_auth
│   │   ├── jwt_auth.py           # Solo helpers get_current_user_jwt / get_current_restaurant_jwt
│   │   ├── subscription.py       # get_subscription_status, is_subscription_active, GRACE_PERIOD_DAYS
│   │   ├── rate_limiter.py       # Anti-bots pedidos
│   │   ├── restaurant.py         # get_current_restaurant
│   │   ├── image_handler.py / mp_webhook.py / cover_bank.py / constants.py / timezone.py
│   ├── static/
│   │   ├── CSS/                  # Tailwind v4 + CSS personalizado (output.css generado)
│   │   ├── js/                   # ~31 módulos Vanilla JS
│   │   └── uploads/              # Caché local imágenes
│   ├── template/                 # Plantillas Jinja2 principales
│   │   ├── auth/ common/ components/ dashboard/ email/ employees/ errors/ rewards/
│   └── templates/                # (dir separado) solo públicas sueltas
│       └── public/subscription_expired.html
├── astro/                        # Frontend menú público (Astro + Tailwind v4) — repo/distinto
├── docs/                         # Documentación
├── migrations/                   # Migraciones Alembic (head: c4c47adbb493)
├── settings.py                   # Configuración (carga .env)
├── run.py                        # Punto de entrada
├── requirements.txt / requirements-dev.txt
└── package.json                  # Dependencias Node (Tailwind CLI, k6)
```

---

## 2. Patrón Arquitectónico

Monolito full-stack: Flask sirve web (Jinja2) + API (JSON). **Astro** es un frontend separado para el menú público (proxy `/menu/api` → Flask). Regla: rutas solo orquestan, la lógica vive en `services/`.

| Capa | Tecnología | Ubicación |
|------|-----------|-----------|
| Web (HTML) | Jinja2 | `app/routes/*.py` (no-api) + `app/template/` |
| API (JSON) | Blueprints `api_*` | `app/routes/api_*.py` (CSRF exento vía before_request) |
| Lógica | `@staticmethod` / clases service | `app/services/**` |
| ORM | SQLAlchemy | `app/models/` (paquete) |
| Frontend | Vanilla JS + Tailwind v4 | `app/static/js/` + `astro/` |

**Servicios** retornan tupla `(resultado, None)` en éxito / `(None, {"error": "..."})` en error.

---

## 3. Autenticación (3 mecanismos)

| Tipo | Mecanismo | Uso |
|------|-----------|-----|
| Sesión | Cookie Flask (`user_id`/`employee_id`) | Dashboard web / portal empleado (PIN) |
| JWT | Bearer (24h) | API móvil/externa |
| Clerk OAuth | Redirect + callback | Web (login social) |

**Decoradores UNIFICADOS** en `app/utils/auth.py` (reemplazan los viejos `@login_required`/`@active_required`/`@flexible_*` de `jwt_auth.py`):
- `require_auth` — login sesión O JWT
- `require_active` — login + cuenta activa (maneja `dormant`, `grace_period`, `expired`)
- `require_feature(name)` — features por plan
- `require_role(*roles)` / `require_role_check` — roles de empleado

`jwt_auth.py` queda solo con helpers `get_current_user_jwt` / `get_current_restaurant_jwt`.

---

## 4. Base de Datos

**MySQL 8** (prod/CI) / **MariaDB XAMPP** (local, `root` sin password, puerto 3306, DB `orderfox`). Driver `mysql+pymysql://`.
**~26 modelos** en `app/models/`, naming `snake_case`, timestamps UTC (`AwareDateTime`).

| Archivo | Modelos clave |
|---------|---------------|
| `core.py` | `Restaurant` (incluye `subscription_state`, `dormant_at`), `User` (role: owner/employee), `Category`, `Product`, `Modifier`, `Table` |
| `orders.py` | `Order`, `OrderItem`, `OrderEvent` (trazabilidad), `OrderCounter` |
| `rewards.py` | `PreRegistration`, `TrialHistory`, `Expense`, `RewardClaim`, `UserAchievement`, `Streak`, `DiscountCoupon` |
| `ai.py` | `CopilotConversation`, `CopilotMessage`, `CopilotBusinessEvent`, `AILlmCall` |
| `cash.py` | `CashRegister` |
| `tokens.py` | `AITokenWallet`, `AITokenTransaction` |

**Trazabilidad de pedidos:** `OrderEvent` + helper `log_event()` / `resolve_actor()` / `serialize_event()`. Cada acción web/API/empleado/público/tarea registra un evento con actor resolvable.

---

## 5. Planes y Estados de Suscripción

| Plan | Precio | Productos | Mesas QR | Modifiers | Tokens IA |
|------|--------|-----------|----------|-----------|-----------|
| **Trial** | Gratis (7d) | Ilimitado | Sí | Sí | 100 |
| **Emprendedor** | 30.000 COP/mes | 25 | No | No | 0 |
| **Crecimiento** | 40.000 COP/mes | 100 | Sí | Sí | 0 |
| **Elite** | 50.000 COP/mes | Ilimitado | Sí | Sí | Ilimitados |

`GRACE_PERIOD_DAYS = 5` en `app/utils/subscription.py` (docs dicen 14; pendiente de subir a 7-14).

**Estados** (`get_subscription_status(restaurant)`):
`active` → `expiring_soon_neutral` → `expiring_soon_warning` → `expiring_soon_urgent` → `grace_period` → `expired` / `dormant` / `inactive` (suspensión admin) / `no_subscription` / `not_found`.

**Ciclo de vida SaaS (sin borrado destructivo):** `manage_subscription_lifecycle` (3 AM) marca cuentas `is_active=False` >30d o suscripción expirada >grace como **`dormant`** (congela CRUD, preserva TODOS los datos). Reactivables en 1 clic desde `dashboard.subscription`. NUNCA se borra el restaurante.

---

## 6. Tareas Programadas (APScheduler)

| Job | Horario | Acción |
|-----|---------|--------|
| `scan_business_events` | Cada hora | Despacha eventos de negocio a Copilot VZ |
| `manage_subscription_lifecycle` | Diario 3:00 AM | Marca inactivos/expirados como `dormant` (SIN borrar datos) |
| `expire_pending_orders` | Cada hora | Marca pedidos `pending` vencidos como `expired` |

Registradas en `init_tasks()` (app/__init__.py). CLI `flask cleanup-accounts` dispara `manage_subscription_lifecycle`.

---

## 7. Integraciones Externas

| Servicio | Propósito | Config |
|----------|-----------|--------|
| **Clerk** | OAuth + JWT | `CLERK_*` |
| **Cloudinary** | Imágenes (max 16MB) | `CLOUDINARY_*` |
| **Mercado Pago** | Pagos | `MP_*` + `api_webhooks.py` |
| **Scanner IA** | AI externa menú | `SCANNER_IA_URL` + `SERVICE_API_KEY` |
| **DeepSeek** | LLM Copilot VZ | `DEEPSEEK_*` |
| **Gmail SMTP** | Correos | `MAIL_*` |

---

## 8. Rate Limiting (pedidos)

`app/utils/rate_limiter.py` — `OrderRateLimiter`:
- **Máx 3 pedidos/min por IP** por restaurante.
- Exceder → **ban 10 min**.
- Honeypot + mínimo **3s** entre checkout y envío.
- `SERVICE_API_KEY` (header `x-api-key`) exime.

---

## 9. Frontend (Vanilla JS + Astro)

**~31 módulos JS** en `app/static/js/` (sin framework). Destacados:
- `cart.js` — carrito localStorage + cross-tab sync
- `orders.js`, `order_create.js`, `orders-realtime.js`, `order-detail-panel.js`, `order_detail.js`
- `products-dashboard.js`, `products.js`, `categories-dashboard.js`, `categories.js`
- `cash-register.js`, `cash-register-copilot.js` — Caja + **Copilot de Caja** (naranja, cobros/pagos/pendientes)
- `insights.js`, `insights_greetings.js` — **Copilot Estratégico** (índigo #6366f1, ventas/rentabilidad/tendencias)
- `subscription.js`, `token-wheel.js`, `reward*`, `streak*`, `achievement*`, `auth-*`, `sync_clerk.js`, `ui-utils.js`, `modal-delete.js`, `image-upload.js`, `payment-modal.js`, `qr_pages.js`, `dashboard.js`, `legal.js`, `register_*.js`, `tailwind.*.js`

**CSS:** Tailwind v4 vía `@tailwindcss/cli` (sin `tailwind.config.js`). `output.css` es generado (`npm run build:css`). Tokens de diseño en `design_tokens.css`.

**Dos "Copilots" diferenciados (2026-08):**
- **Copilot Estratégico** (`/insights/`, índigo): estrategia de negocio, recomendaciones, preguntas abiertas. Prompt `v1.3`.
- **Copilot de Caja** (en caja registradora, naranja): cobros, pagos, pendientes; hace cross-sell hacia el Estratégico.

**Astro** (`astro/`): menú digital público (SSR). Puerto 4321, proxy `/menu/api` → Flask. Si tocás menú público, editás `astro/src/`, no `app/template/`.

---

## 10. Copilot VZ (Estratégico)

Blueprint propio en `app/routes/insights.py` (fuera del dashboard). Paquete `app/services/insights/`:
- `classifier.py`: híbrido `quick` (SQL directo, gratis) vs `analysis` (DeepSeek, 1 token de `AITokenWallet`).
- `message_handler.py`: sanitización anti-inyección (patrones `ignore previous instructions`, etc.) + límite 2000 chars. **NUNCA quitar.**
- `llm_service.py`: `validate_llm_response()` antes de mostrar al usuario.
- `context_manager.py`: compresión 2 fases al superar 80%/85% de 12K tokens.
- `prompt_builder.py`: `PROMPT_VERSION = "v1.3"`, cada conversación guarda su versión.
- Seguimiento (`analysis_active=True`) no descuenta crédito pero sí paga DeepSeek.

---

## 11. Manejo de Timezone

**Regla de oro:** todo en UTC. `datetime.now(timezone.utc)` siempre. `AwareDateTime` maneja BD↔Python.

---

## 12. Gotchas / Reglas de Seguridad

- **Paquetes:** verificar con `pip index versions <pkg>` antes de instalar (evitar alucinaciones). `python-jose` eliminado (migrado a PyJWT 2.13).
- **Inyección IA:** no modificar `message_handler.py` ni pasar secrets en system prompt.
- **CSRF:** `WTF_CSRF_CHECK_DEFAULT=False` + `before_request` manual exime `/api/*` e `/insights/api/*`. No usar `@csrf.exempt` por endpoint.
- **Server header:** se parchea en `run.py` (`WSGIRequestHandler`), no en `app/__init__.py`.
- **DB local:** MariaDB XAMPP (root sin pass). El MCP `Conexion_MYSQL` apunta a ella; si falla, usar `flask db` CLI o pymysql.
- **Rate limiter** en memoria (se pierde al reiniciar).

---

## 13. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial de esta guía | Auditoría Documental |
| 2026-08-06 | 1.4 | Botón "Analizar" ejecuta análisis automático (`api_consume_event` → `handle_post_message`) | Agente |
| 2026-08-22 | 2.0 | Reescritura completa: modelos en `app/models/` (paquete), decoradores unificados en `auth.py`, Copilot VZ (Estratégico, índigo) + Copilot de Caja (naranja), trazabilidad de pedidos (`OrderEvent`), ciclo de vida `dormant` sin borrado, Astro como frontend de menú, Tailwind v4, rate limiting 3/min+ban 10min | Agente |

# Changelog

Todas las fechas en UTC.

---

## [1.5.0] — 2026-08-17

### Rediseño del Dashboard Home

Reestructuración completa del dashboard principal con layout de grid 2 columnas, cards de color semáforo, gráficas Chart.js y métricas de caja en tiempo real.

### Añadido

- **Layout grid 2 columnas** en `index.html`: Hero 100%, 3 contadores 33% cada uno, barras+dona 50/50, productos+revenue 50/50, menú digital 100%. Mobile stacks a 1 columna.
- **3 cards de estado con color semáforo**: Pendientes `#FF7A29` naranja, Confirmados `#30A46C` verde, Entregados `#3B82F6` azul. Fondos `rgba()` al 12% opacidad, sin bordes, texto blanco.
- **Gráfica de barras** (`initWeeklyChart`): ventas semanales por día con toggle `$`/`#`.
- **Gráfica de dona** (`initDoughnutChart`): distribución pendientes/confirmados/entregados. Colores: `['#FF7A29', '#30A46C', '#3B82F6']`.
- **Gráfica de tendencia de ingresos** (`initRevenueChart`): línea con 30 días de datos, área sombreada.
- **Sección de productos Top 5** con toggle Hoy/30d.
- **Alerta de pedidos expirados**: visible solo cuando `expired_count > 0`. Fondo `#2D1A0A`, borde `#FF7A29`, texto naranja.
- **Métrica "Cobrado hoy"** en hero: muestra pagos reales en caja. Oculta cuando `vendido == cobrado` o ambos cero. Alerta `#FF7A29` cuando `vendido > cobrado`.
- **4 endpoints API** con `@require_role('owner')`:
  - `GET /dashboard/api/weekly-stats` → ventas e pedidos por día (7 días)
  - `GET /dashboard/api/top-products?days=30` → productos más vendidos
  - `GET /dashboard/api/collected-today` → vendido vs cobrado
  - `GET /dashboard/api/revenue-trend` → tendencia 30 días
- **`weekly_sales_by_day()`** en `data_service.py`: ventas diarias por día de la semana en TZ Colombia.
- **`revenue_trend_30d()`** en `data_service.py`: ventas diarias de los últimos 30 días.
- **`expired_today`** en `get_today_overview()`: cuenta pedidos expirados hoy (query por `updated_at`).
- **`CSP connect-src`**: agregado `cdn.jsdelivr.net` para Chart.js source maps.
- **Employee logout**: ahora redirige al login del empleado (no al admin). Guarda `session['employee_slug']` al login.
- **Confirmación al cancelar**: `orders.js` muestra `confirm()` antes de cancelar un pedido desde la lista.

### Cambiado

- **`dashboard_service.py:_get_date_range()`** — rangos calculados en hora de Colombia (UTC-5), consistente con CashRegisterService. Retorna `(start, end)` donde `end` es exclusivo.
- **`dashboard_service.py:get_today_overview()`** — ventas ahora usan `_paid_base_query` (pagados, status != cancelled, payment_method NOT NULL). Antes usaba `status.in_(['confirmed', 'delivered'])` que incluía no pagados.
- **`dashboard_service.py:get_extended_stats()`** — alineado con mismos criterios de caja.
- **`dashboard.js` v4** — refactor completo: `setChartMode($/#)`, `setProductsMode(Hoy/30d)`, `fetchCollectedToday()`, `fetchTopProducts()`, `initRevenueChart()`. Polling cada 30s.
- **`_orders_list.html`** — badges y bordes de pedidos usan colores semáforo. Headers de sección coloreados.
- **`order_detail.html`** — mensaje de cancelar corregido: "El pedido cambiará a estado cancelado. Puedes restaurarlo después desde la lista de cancelados."
- **`order_create.html` / `order_create_pos.html`** — nombre del cliente ahora es opcional. Eliminado `required` y texto "obligatorio".
- **`order_service.py:create_order()`** — `customer_name` ya no lanza `ValueError` si está vacío.
- **`cashier.html`** — 4 botones de pago: Efectivo, Nequi, **Bancolombia** (amarillo), Tarjeta. Grid `grid-cols-2`.
- **`auth.py` login** — limpia `session['employee_slug']` al entrar como dueño.

### Seguridad

- **4 endpoints de dashboard** protegidos con `@require_role('owner')`: stats, ai-stats, weekly-stats, top-products, collected-today, revenue-trend.
- **Dashboard index** protegido con `@require_role('owner')`.

### Seguridad — Roles y permisos (v2.1.0)

Implementación completa del sistema de roles: `owner`, `cashier`, `waiter`.

#### Añadido

- **`require_role(*roles)`** en `app/utils/auth.py`: decorador que verifica que el usuario autenticado tiene uno de los roles permitidos. Soporta sesión Flask y Bearer JWT (API móvil). Redirige a portal de empleado si no tiene permisos.
- **`require_role_check(*roles)`** en `app/utils/auth.py`: función reutilizable para `before_request`. Retorna None si pasa; respuesta JSON 403 o redirect si no.
- **`_EMPLOYEE_ALLOWED_ENDPOINTS`** en `app/routes/orders.py`: whitelist de endpoints que los empleados pueden usar desde su portal (`change_status`, `register_payment`).
- **`_require_dashboard_owner()`** en `app/routes/orders.py`: `before_request` que bloquea empleados en rutas de pedidos del dashboard, salvo los endpoints permitidos.
- **`app/routes/employees.py`** (nuevo): portal de empleado con login PIN, menú de pedidos, caja registradora.

#### Cambiado

- **`require_auth`** — ahora acepta `employee_id` en sesión (portal del empleado). Antes solo aceptaba `user_id`.
- **`_get_restaurant_unified`** — busca restaurante por `user_id` O `employee_id`.
- **`require_active`** — identifica al dueño por `role='owner'` (no `users[0]`). Corrige bug donde el primer usuario podía ser un empleado.
- **`require_role('owner')`** agregado a endpoints protegidos:
  - `GET /dashboard/` — solo dueño
  - `GET /dashboard/api/stats` — solo dueño
  - `GET /dashboard/api/ai-stats` — solo dueño
  - `GET /dashboard/api/weekly-stats` — solo dueño
  - `GET /dashboard/api/top-products` — solo dueño
  - `GET /dashboard/api/collected-today` — solo dueño
  - `GET /dashboard/api/revenue-trend` — solo dueño
  - `POST /orders/create` — solo dueño
  - `POST /orders/<id>/cancel` — solo dueño
  - `POST /orders/<id>/delete` — solo dueño
- **`require_role('owner', 'cashier', 'waiter')`** en `PATCH /orders/<id>/status` — todos los roles pueden cambiar estado.
- **`require_role('owner', 'cashier')`** en `POST /orders/<id>/payment` — solo dueño y cajero registran pago.
- **`app/routes/dashboard.py:achievements()`** — identifica dueño por `role='owner'` (no `users[0]`).

#### Flujo de empleados

1. **Login**: empleado ingresa PIN en `/empleado/<slug>` → sesión `employee_id`
2. **Portal**: ve pedidos activos, puede cambiar estados, registrar pagos
3. **Bloqueo**: no puede acceder a `/dashboard/`, `/orders/create`, cancelar/eliminar pedidos
4. **Logout**: vuelve al login del empleado (no al admin)

#### Archivos modificados (roles)

| Archivo | Cambios |
|---------|---------|
| `app/utils/auth.py` | `require_role`, `require_role_check`, `require_auth` acepta `employee_id` |
| `app/routes/orders.py` | `before_request` con whitelist, `@require_role` en endpoints |
| `app/routes/dashboard.py` | `@require_role('owner')` en index y 6 API endpoints |
| `app/routes/employees.py` | **Nuevo**: portal completo de empleado |

---

### Archivos modificados (rediseño dashboard)

| Archivo | Cambios |
|---------|---------|
| `app/routes/dashboard.py` | 4 endpoints API, `cobrado_hoy`, `expired_count`, `@require_role('owner')` |
| `app/services/dashboard_service.py` | `_get_date_range()` en Colombia TZ, `expired_today`, ventas con `_paid_base_query` |
| `app/services/insights/data_service.py` | `weekly_sales_by_day()`, `revenue_trend_30d()` |
| `app/static/js/dashboard.js` | v4 completo: charts, polling, toggles |
| `app/static/js/orders.js` | `confirm()` antes de cancelar |
| `app/template/dashboard/index.html` | Layout grid 2-col, cards color, dona, revenue, alerta expirados |
| `app/template/dashboard/_orders_list.html` | Colores semáforo en badges y bordes |
| `app/template/dashboard/order_detail.html` | Mensaje de cancelar corregido |
| `app/template/dashboard/order_create.html` | Nombre opcional |
| `app/template/employees/order_create_pos.html` | Nombre opcional, details colapsado |
| `app/template/employees/cashier.html` | 4 botones de pago (Bancolombia agregado) |
| `app/services/order_service.py` | `customer_name` opcional |
| `app/routes/employees.py` | **Nuevo**: logout redirige a login del empleado, guarda `employee_slug` en sesión |
| `app/routes/auth.py` | Limpieza de `employee_slug` en login |
| `app/routes/employees.py` | Logout redirige a login del empleado |
| `app/__init__.py` | CSP `cdn.jsdelivr.net` en `connect-src` |

### Cómo probar

1. **Dashboard**: `python run.py` → ir a `/dashboard/` → verificar grid 2-col, cards de color, gráficas con datos.
2. **Alerta expirados**: crear un pedido pending, esperar 24h (o modificar `expires_at` en DB), verificar que aparece la alerta.
3. **Cancelar desde lista**: presionar "Rechazar" → verificar que aparece `confirm()`.
4. **Logout empleado**: login con PIN → cerrar sesión → verificar que vuelve al login del empleado, no al admin.
5. **Roles**: login como empleado → intentar acceder a `/dashboard/` → debe redirigir al portal del empleado. Login como dueño → puede acceder a todo.
6. **Tests**: `pytest tests/ -x -q` → 434 tests pasan.

---

## [1.4.2] — 2026-07-21

### Seguridad — Race conditions en tokens IA

Auditoría completa del flujo de tokens identificó 5 vectores explotables. Todos parcheados.

### Añadido
- **`POST /api/v1/webhooks/mercadopago`** — endpoint dedicado de webhooks con verificación de firma HMAC-SHA256 (`x-signature`) e idempotencia por `data.id`. Reemplaza el endpoint `/webhook` legacy (sin verificación).
- **`app/utils/mp_webhook.py`** — utilidades compartidas `extract_mp_signature()` y `verify_mp_signature()` reutilizables por cualquier endpoint de webhook.
- **Variable `MP_WEBHOOK_SECRET`** en `settings.py` y `.env.example`. Si está configurado, los webhooks rechazan peticiones con firma inválida (fail-closed).
- **Migración Alembic** `a4b2c3d4e5f6`: índice UNIQUE sobre `ai_token_transactions.mp_payment_id`. MySQL permite múltiples NULLs, así que los consumos sin referencia MP no se bloquean.

### Cambiado
- **`TokenService.consume_token()`** — lock pesimista `SELECT ... FOR UPDATE` sobre la billetera. Cierra el TOCTOU que permitía doble consumo cuando un usuario tenía 1 token restante y disparaba 2 requests concurrentes.
- **`TokenService.credit_topup_purchase()`** — `UPDATE ... SET extra_tokens = extra_tokens + N` atómico en SQL. Reemplaza el read-then-write que causaba lost updates al acreditar top-ups.
- **`initialize_or_reset_token_wallet()`** — lock pesimista en el bloque de creación + UPDATE atómico en el reset mensual. Evita duplicación de wallets y race conditions en el reset del plan.
- **`app/routes/auth.py:webhook()`** — el endpoint legacy ahora también valida firma HMAC cuando `MP_WEBHOOK_SECRET` está configurado.
- **`app/models.py`** — `AITokenTransaction.mp_payment_id` ahora es `unique=True` en la capa de modelo (la migración ya lo aplica a nivel DB).

### Operacional
- `flask db upgrade` necesario en el siguiente deploy para aplicar la migración.
- Configurar `MP_WEBHOOK_SECRET` en el `.env` del servidor con la clave que da Mercado Pago en su dashboard de Webhooks.

---

## [1.4.1] — 2026-07-18

### Añadido
- **Pantalla completa para Copilot VZ** — nuevo `base_fullscreen.html` que elimina sidebar del dashboard, banners de suscripción y `md:ml-[260px]`; el body es `flex flex-col overflow-hidden` para llenar el viewport
- **Saludo dinámico** — rotación aleatoria entre 8 frases profesionales en cada nuevo chat (ya no dice "soy tu Copilot VZ")
- **Factorización masiva de templates**: todo `<style>` y `<script>` inline extraído a archivos CSS/JS externos
  - `insights.html`: 1740 → 29 líneas (7 partials + CSS/JS externos)
  - `legal.html`: 746 → 174 líneas
  - `auth/index.html`: 334 → 152 líneas
  - `auth/plans.html`: 509 → 282 líneas
  - `auth/register_setup.html`, `register_verify.html`, `sync_clerk.html`, `receipt.html`
- Nuevos archivos CSS estáticos: `insights.css`, `legal.css`, `plans.css`, `auth_index.css`, `receipt.css`, `register_setup.css`, `register_verify.css`
- Nuevos archivos JS estáticos: `insights_greetings.js`, `legal.js`, `auth_index.js`, `register_setup.js`, `register_verify.js`, `sync_clerk.js`
- Nuevos partials para Copilot VZ: `insights_sidebar.html`, `insights_chat.html`, `insights_mobile_nav.html`, `insights_modals.html`
- Agentes opencode: `astro-page-builder`, `db-migration-handler`, `flask-blueprint-generator`, `test-suite-runner`

### Cambiado
- **insights.js** — refactor: eliminación de lógica duplicada, limpieza de funciones obsoletas, mejora de scroll-to-bottom
- **AGENTS.md** — actualizado con nuevos agentes y comandos
- **`settings.py`** y **`package.json`** — dependencias y configuración actualizadas
- Templates auth y dashboard: eliminación de código inline duplicado, carga diferida de recursos
- CSRF: exenciones refinadas en `app/csrf.py` y `app/routes/api_public.py`

### Eliminado
- `LICENSE` — archivo de licencia removido
- `app/static/img/Zorro.png` — imagen no utilizada
- ~3277 líneas de código inline de templates (CSS/JS embebido)

### Cómo probar
1. `flask run` — navegar a `/insights/` — debe cargar en pantalla completa sin sidebar del dashboard
2. Verificar sidebar en desktop (visible, con perfil y botones de navegación)
3. Click en "Nuevo Chat" — saludo cambia aleatoriamente
4. Abrir/cerrar drawer en mobile (< 768px)
5. Verificar que modales (renombrar, eliminar, contexto, chart, onboarding) funcionan
6. Verificar que `legal.html` carga correctamente con estilos externos
7. Verificar que `auth/plans.html` y `auth/index.html` mantienen diseño original con CSS externo
8. `npm run build:css` — verificar que no hay roturas en estilos compilados

---

## [1.4.0] — 2026-07-15

### Añadido
- **Copilot VZ** — Analista de negocios IA completamente funcional
  - Clasificador híbrido (SQL rápido + análisis profundo con DeepSeek)
  - Prompt builder con 12 reglas estrictas de identidad, estilo y alcance
  - Context manager con compresión en 2 fases (resumen + modo comprimido)
  - Sistema de gráficas automáticas (Chart.js + sanitizer)
  - Onboarding inteligente según madurez de datos (4 niveles)
  - Sugerencias dinámicas de bienvenida y seguimiento contextual
  - Motor de eventos automáticos (APScheduler)
  - Anillo de contexto SVG con persistencia
  - Disclaimer "Copilot VZ puede cometer errores" inteligente
  - Edición de mensajes y regeneración de respuestas
  - Conversaciones ancladas, búsqueda y renombrado
- **Frontend Astro standalone** para el menú digital público
  - Migración completa del menú QR a Astro
  - URLs redirigidas desde Flask al nuevo frontend
- Documentación completa de Copilot VZ (GUIDE-07)

### Cambiado
- Migración del menú público de Flask/Jinja2 a Astro
- Dashboard: rediseño Friendly AI-Centric (Velzia)
- Panel de suscripción: diseño renovado en pestañas (Plan Actual, Historial, Planes)
- Autenticación: flujo Clerk sync simplificado, plantillas login pulidas
- Sidebar/navbar: logo y marca actualizados en todas las páginas
- Modal de compra de tokens con packs de 5K y 10K
- `AGENTS.md` actualizado con guía de Copilot VZ
- Logo del zorro reemplazado por robot chef en el menú digital (Astro favicon)
- System prompt de Copilot VZ: versión v1.3 (regla de identidad vs nombre del restaurante)

### Arreglado
- Disclaimer de Copilot VZ no aparecía en conversaciones nuevas
- Botón de "Editar" en página de perfil del dashboard corregido
- Pantalla de error 429 rediseñada y 500 estilizada
- Varias correcciones en templates auth y dashboard

---

### Añadido
- Sistema de tokens AI (Velzia 2.0.0)
  - `AITokenWallet` por usuario con plan_tokens + extra_tokens
  - `AITokenTransaction` como log inmutable de operaciones
  - Plan Elite con tokens ilimitados
  - Top-up packs via Mercado Pago (5K = 15 tokens, 10K = 35 tokens)
- `PreRegistration` — pre-registro con selección de plan
- `Expense` — registro de gastos del restaurante
- `OrderCounter` — contador atómico diario para números de orden

### Cambiado
- Clerk JWT como método de autenticación para Scanner IA
- `is_active` ahora controla visibilidad del restaurante (no acceso)

---

## [1.2.0] — 2026-03-01

### Añadido
- Rate limiting inteligente con detección de patrones de spam
- Sistema de período de gracia de 14 días post-expiración
- PWA con Workbox service workers + Dexie IndexedDB
- Plantillas de error personalizadas (400, 403, 404, 429, 500)

### Cambiado
- Refactor: lógica de negocio extraída a `app/services/`
- Timezone: sanitización completa a UTC con `AwareDateTime`
- `get_subscription_status()` como fuente única de verdad

---

## [1.1.0] — 2026-01-15

### Añadido
- Autenticación con Clerk OAuth
- Integración con Cloudinary para imágenes
- Integración con Mercado Pago para pagos de suscripción
- Tareas programadas con APScheduler

### Cambiado
- Migración de SQLite a MySQL 8.x
- Arquitectura de rutas: patrón de doble blueprint (web + API)

---

## [1.0.0] — 2025-11-01

### Añadido
- Lanzamiento inicial de Orderfox
- CRUD completo de restaurantes, productos, categorías, modificadores
- Menú público con QR por mesa
- Sistema de pedidos en tiempo real
- Dashboard del dueño con estadísticas
- Planes de suscripción (Emprendedor, Crecimiento, Elite)
- Trial de 7 días con auto-creación de cuenta
- Autenticación tradicional (email + password)

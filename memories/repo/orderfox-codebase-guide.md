# Guía de Arquitectura del Código Base — Orderfox

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Versión del Proyecto:** 1.3.0

---

## 1. Estructura General del Proyecto

```
Orderfox/
├── app/                          # Paquete principal de la aplicación
│   ├── __init__.py               # App factory (create_app)
│   ├── models.py                 # Modelos SQLAlchemy (11 tablas)
│   ├── extensions.py             # Inicialización de Flask extensions
│   ├── csrf.py                   # Gestión de CSRF (Flask-WTF)
│   ├── tasks.py                  # Tareas programadas (APScheduler)
│   ├── routes/                   # Blueprints (17 módulos)
│   │   ├── auth.py               # Autenticación web
│   │   ├── dashboard.py          # Dashboard web del dueño
│   │   ├── categories.py         # CRUD de categorías (web)
│   │   ├── products.py           # CRUD de productos (web)
│   │   ├── orders.py             # Gestión de pedidos (web)
│   │   ├── tables.py             # Gestión de mesas (web)
│   │   ├── public.py             # Ruta pública de pedidos
│   │   ├── menu.py               # Menú público del restaurante
│   │   ├── tokens.py             # Gestión de tokens AI (API)
│   │   ├── api_auth.py           # API de autenticación
│   │   ├── api_dashboard.py      # API del dashboard
│   │   ├── api_categories.py     # API de categorías
│   │   ├── api_products.py       # API de productos
│   │   ├── api_orders.py         # API de pedidos
│   │   └── api_tables.py         # API de mesas
│   │   └── api_public.py         # API pública
│   │   └── api_menu.py           # API de menú
│   ├── services/                 # Capa de lógica de negocio
│   │   ├── auth_service.py       # Registro, login, Clerk sync
│   │   ├── order_service.py      # CRUD de pedidos
│   │   ├── product_service.py    # CRUD de productos
│   │   ├── category_service.py   # CRUD de categorías
│   │   ├── table_service.py      # CRUD de mesas + QR
│   │   ├── dashboard_service.py  # Estadísticas del dashboard
│   │   ├── public_menu_service.py# Menú y pedidos públicos
│   │   └── token_service.py      # Wallet de tokens AI
│   ├── utils/                    # Utilidades
│   │   ├── subscription.py       # Estado de suscripción
│   │   ├── rate_limiter.py       # Rate limiting inteligente
│   │   ├── jwt_auth.py           # Decoradores JWT
│   │   ├── restaurant.py         # Helper de restaurante actual
│   │   └── image_handler.py      # Subida/eliminación de imágenes
│   ├── forms/                    # Formularios WTForms
│   │   ├── auth.py               # Formularios de autenticación
│   │   └── dashboard.py          # Formularios del dashboard
│   ├── static/
│   │   ├── CSS/                  # Tailwind + CSS personalizado
│   │   ├── js/                   # 23 módulos Vanilla JS
│   │   └── uploads/              # Caché local de imágenes
│   └── template/                 # Plantillas Jinja2
│       ├── auth/                 # Login, registro, recovery
│       ├── common/               # Layouts base, navegación
│       ├── components/           # Componentes reutilizables
│       ├── dashboard/            # Vistas del dashboard
│       ├── public/               # Menú público del cliente
│       ├── email/                # Plantillas de correo
│       └── errors/               # Páginas de error
├── docs/                         # Documentación del proyecto
├── migrations/                   # Migraciones Alembic
├── settings.py                   # Configuración de Flask
├── run.py                        # Punto de entrada
├── requirements.txt              # Dependencias Python
└── package.json                  # Dependencias Node.js
```

---

## 2. Patrón Arquitectónico: Monolito Full-Stack

El proyecto NO usa una API separada del frontend. Flask sirve ambas caras:

| Capa | Tecnología | Ubicación |
|------|-----------|-----------|
| **Web (HTML)** | Jinja2 + Flask routes | `app/routes/*.py` + `app/template/` |
| **API (JSON)** | Flask blueprints | `app/routes/api_*.py` |
| **Lógica de negocio** | Clases @staticmethod | `app/services/*.py` |
| **ORM** | SQLAlchemy | `app/models.py` |
| **Frontend** | Vanilla JS + Tailwind CSS | `app/static/js/` + `app/static/CSS/` |

### Patrón de Doble Blueprint

Cada dominio tiene DOS blueprints: uno para HTML (web) y otro para JSON (API):

```
/products/list          → HTML (dashboard)
/api/products/list      → JSON (mobile/IA)
```

### Patrón de Servicios

Los servicios siguen una convención consistente:
```python
@staticmethod
def metodo(param):
    # éxito → retorna (resultado, None)
    # error → retorna (None, {"error": "mensaje"})
    return (resultado, None)
```

---

## 3. Sistema de Autenticación (3 Capas)

| Tipo | Mecanismo | Uso |
|------|-----------|-----|
| **Sesión** | Cookie Flask | Dashboard web |
| **JWT** | Bearer token (24h) | API móvil/externa |
| **Clerk OAuth** | Redirect + callback | Web (login social) |

Decoradores en `app/utils/jwt_auth.py`:
- `@login_required` / `@jwt_login_required` — auth simple
- `@active_required` / `@jwt_active_required` — auth + suscripción activa
- `@flexible_login_required` / `@flexible_active_required` — acepta sesión O JWT

---

## 4. Base de Datos (MySQL 8.x)

**11 modelos** con naming `snake_case` y timestamps UTC:

| Modelo | Tabla | Propósito |
|--------|-------|-----------|
| `Restaurant` | `restaurants` | Tenant (negocio) |
| `User` | `users` | Staff/owner |
| `Category` | `categories` | Agrupación de productos |
| `Product` | `products` | Items del menú |
| `Modifier` | `modifiers` | Extras (toppings, tamaños) |
| `Order` | `orders` | Pedidos de clientes |
| `OrderItem` | `order_items` | Items dentro de un pedido |
| `Table` | `tables` | Mesas físicas |
| `TrialHistory` | `trial_history` | Control de trials únicos |
| `AITokenWallet` | `ai_token_wallets` | Balance de tokens AI |
| `AITokenTransaction` | `ai_token_transactions` | Log de transacciones |
| `PreRegistration` | `pre_registrations` | Pre-registros de usuarios |
| `OrderCounter` | `order_counters` | Contador atómico diario |
| `Expense` | `expenses` | Gastos del restaurante |

**Convenciones:**
- `AwareDateTime` decorator — convierte UTC <-> naive automáticamente
- Timestamps: `created_at`, `updated_at` en todos los modelos
- Cascade deletes: `ondelete='CASCADE'` en relaciones principales
- `Order.ip_address` indexado para rate limiting

---

## 5. Planes de Suscripción

| Plan | Precio | Productos | Mesas QR | Modifiers | Tokens AI |
|------|--------|-----------|----------|-----------|-----------|
| **Trial** | Gratis (7d) | Ilimitado | Sí | Sí | 100 |
| **Emprendedor** | 30.000 COP/mes | 25 | No | No | 0 |
| **Crecimiento** | 40.000 COP/mes | 100 | Sí | Sí | 0 |
| **Elite** | 50.000 COP/mes | Ilimitado | Sí | Sí | Ilimitados |

La función central `get_subscription_status(restaurant)` en `app/utils/subscription.py` calcula el estado: `active` → `trial` → `grace_period` → `expired`.

---

## 6. Tareas Programadas (APScheduler)

Jobs definidos en `app/tasks.py`:

| Job | Horario | Acción |
|-----|---------|--------|
| `delete_inactive_accounts()` | Diario 3:00 AM | Elimina restaurantes inactivos >24h |
| `expire_pending_orders()` | Cada hora | Marca pedidos como 'expired' |

---

## 7. Integraciones Externas

| Servicio | Propósito | Configuración |
|----------|-----------|---------------|
| **Clerk** | OAuth + JWT | `CLERK_*` env vars |
| **Cloudinary** | Hosting de imágenes | `CLOUDINARY_*` env vars |
| **Mercado Pago** | Pagos | `MP_*` env vars |
| **Scanner IA** | AI externa | `SCANNER_IA_URL` + `SERVICE_API_KEY` |
| **Gmail SMTP** | Correos | `MAIL_*` env vars |

---

## 8. Rate Limiting

Estrategia en `app/utils/rate_limiter.py`:
- **Normal:** 5 pedidos/minuto (12s mínimo entre pedidos)
- **Sospechoso:** 2 pedidos/minuto (30s mínimo)
- **Detección:** 3+ intentos fallidos en 2 minutos desde misma IP
- **Exención:** Header `x-api-key: <key>` (Scanner IA)

---

## 9. Frontend

**23 módulos JS** en Vanilla (sin framework):
- `cart.js` (511 lines) — Carrito con localStorage + cross-tab sync
- `orders.js`, `order_create.js`, `orders-realtime.js`, `order-detail-panel.js` — Gestión de pedidos
- `products-dashboard.js`, `products.js` — CRUD de productos
- `categories-dashboard.js`, `categories.js` — CRUD de categorías
- `modifiers-modal.js` — Modal de modificadores
- `subscription.js`, `token-wheel.js` — Suscripción y tokens
- `auth-common.js` — Helpers de Clerk
- `ui-utils.js` — Toast, utilidades

**PWA:** Workbox service workers + Dexie (IndexedDB) para offline.

---

## 10. Manejo de Timezone

**Regla de oro:** Todas las fechas en UTC. `datetime.now(timezone.utc)` siempre.
`AwareDateTime` type decorator maneja la conversión automática BD ↔ Python.

---

## 11. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |

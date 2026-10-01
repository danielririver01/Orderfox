# 01 — Velzia Core

Velzia Core es la app Flask original del monorepo (`app/`, puerto **5000**).
En la arquitectura multi-vertical es la **única fuente de verdad** para
identidad, facturación, suscripciones, Copilot VZ y el Hub de Mundos. Los
módulos (como Verduras) son presentación + lógica de su vertical y le
delegan todo lo demás.

## Responsabilidades (lo que SOLO vive en core)

| Área | Dónde | Nota |
|------|-------|------|
| Auth de cuentas (dueños) | `app/routes/auth.py`, `app/services/auth_service.py` | Login/registro de la cuenta SaaS; Clerk como proveedor |
| Registro de tenants | `app/services/business_registration.py` | El alta de tenants vive SOLO aquí; los módulos jamás crean tenants |
| Billing y suscripciones | `app/services/user_billing.py`, `app/services/subscription_service.py`, `app/utils/subscription.py` | Máquina trial → activo → gracia → dormant; fuente única `get_subscription_status()` |
| Copilot VZ | `app/services/insights/` | **ÚNICO.** Los submódulos se conectan por `business_id`; nunca construyen copilotos propios |
| Hub de Mundos | `app/routes/auth.py` (`register_vertical`), `app/routes/dashboard.py` (`mundos`, `mundos_pos`) | Selector, tarjetas, handoff SSO (ver `02-mundos.md`) |
| Schedulers | `app/__init__.py` + `app/tasks.py` | Lifecycle de suscripciones, expiración de pedidos, eventos de negocio |
| API del mundo Restaurante | `app/routes/api_*.py`, `app/routes/public.py`, `app/routes/cash_register.py` | Pedidos, menú público, caja, reservas |
| Menú digital | Redirección a Astro (`ASTRO_BASE_URL`) | Si tocas el menú público, editas `astro/src/`, no `app/template/` |

## Entrypoints y puertos

| Pieza | Entrada | Puerto |
|-------|---------|--------|
| Velzia Core | `run.py` → `app.create_app()` | 5000 |
| Menú público (Astro) | `astro/` (`npm run dev`), proxya `/menu/api` a Flask | 4321 |
| Mundo Verduras | `verduras/run.py` → `verduras.app_factory.create_app()` | 5100 |

`run.py` ejecuta `app = create_app()` a nivel de módulo y aplica el parcheo
del header `Server` (ver gotchas en `AGENTS.md`). `settings.py` carga todo
de `.env`; no subir `.env` a git.

## Config cross-app (en `.env` de la raíz)

| Variable | Quién la lee | Default |
|----------|--------------|---------|
| `DATABASE_URL` | Todos (es el canal de integración) | `postgresql://orderfox:orderfox2026@localhost:5432/orderfox` |
| `VERDURAS_BASE_URL` | Core (redirect del handoff SSO) | `http://localhost:5100` |
| `CORE_BASE_URL` | Módulo verduras (enlace de renovación) | `http://localhost:5000` |

El módulo verduras lee el `.env` de la raíz con sus propios `settings.py`;
no tiene `.env` propio.

## Reglas que no se rompen

1. **Las rutas no tienen lógica de negocio.** Reciben request, llaman un
   service, devuelven response.
2. **No duplicar lógica.** Si un patrón aparece dos veces, se extrae a un
   service o componente compartido.
3. **No agregar dependencias sin justificación.**
4. **Timezone:** todo en UTC, siempre `datetime.now(timezone.utc)`. Los
   modelos usan `AwareDateTime`.
5. **API responses:** `{"success": bool, "message": "...", "data": {...}}`
   o `{"error_code": "..."}`.
6. **CSRF:** exento en `/api/*` (APIs con header, no formularios).
7. **`settings.APP_VERSION`** sincronizado con el último tag git.

## Lo que core expone a los módulos

- Tabla `businesses` (ver `05-datos.md`) + tokens `pos_setup_token` y
  `pos_sso_token` / `pos_sso_expires_at`.
- `GET /api/businesses`-equivalentes internos vía ORM compartido
  (los módulos leen la misma `DATABASE_URL`).
- Redirect de handoff: `dashboard.mundos_pos` →
  `{VERDURAS_BASE_URL}/pos/sso/<slug>/<token>`.
- Enlace de renovación: el módulo apunta a `{CORE_BASE_URL}/renew`.
- Pagos MercadoPago con `external_reference` `biz:<id>:<plan>`; al
  confirmarse, el módulo vuelve a operar sin intervención.

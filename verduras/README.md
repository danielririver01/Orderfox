# Verduras — módulo vertical (app Flask propia)

Primer vertical no-restaurante de Velzia. App Flask **separada** dentro del
monorepo Orderfox: su propia factory, sus settings, sus blueprints y sus
tests. Comparte la DB con velzia core y se integra a través del puente
`Business` ↔ `Restaurant` (rama `feature/verduras`).

## Ejecutar

```bash
# Desde la raíz del monorepo (venv de core activado):
.venv/Scripts/python verduras/run.py        # http://localhost:5100
```

Puertos: core `5000` · Astro `4321` · **verduras `5100`**

## Tests

```bash
pytest verduras/tests        # desde la raíz del monorepo
```

No se collecionan en la suite de core (`pytest.ini` limita `testpaths` a
`tests/`); son independientes y usan sqlite in-memory igual que core.

## Contrato con velzia core

| Regla | Detalle |
|-------|---------|
| **DB compartida** | El módulo lee/escribe la misma `DATABASE_URL` de core. Es el canal de integración principal. |
| **`db` es LA de core** | `verduras/extensions.py` re-exporta `app.models.db`. Nunca instanciar otro `SQLAlchemy()`. |
| **Solo `business_id`** | Toda FK nueva del módulo apunta a `businesses.id`. **Nunca** crear FKs hacia `restaurants`. |
| **Vertical explícito** | Un Business es tenant de este módulo si `vertical == 'verduras'` y `is_active`. Los espejos `vertical='restaurant'` no lo son. |
| **Punto único de contacto** | Todo acceso a `Business` pasa por `verduras/services/context.py`. Si el módulo se extrae, solo ese archivo cambia a cliente HTTP. |
| **Migraciones** | Cadena PROPIA del módulo: `verduras/migrations/` con `version_table='alembic_version_verduras'` y filtro a solo tablas `verduras_*`. Core es dueño del resto del esquema (`businesses` incluida); su `env.py` excluye `verduras_*` de su autogenerate. Las dos cadenas conviven en la misma DB sin tocarse. |

## Endpoints actuales (v0.1.0 — esqueleto)

| Método | Ruta | Qué hace |
|--------|------|----------|
| GET | `/` | Identidad del módulo (nombre, versión) |
| GET | `/health` | Liveness/readiness: proceso + DB compartida |
| GET | `/health/core-bridge` | Diagnóstico: espejos de restaurantes vs businesses verduras |
| GET | `/api/businesses` | Lista Businesses del vertical `verduras` (activos) |
| GET | `/api/businesses/<id>` | Detalle validado (404 si no existe, 409 si es de otro vertical) |
| GET | `/api/verduras/businesses/<bid>/categories` | Listar categorías del business |
| POST | `/api/verduras/businesses/<bid>/categories` | Crear categoría (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/products` | Listar productos (filtro `?category_id=`) |
| POST | `/api/verduras/businesses/<bid>/products` | Crear producto con precio inicial (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/products/<pid>` | Detalle + historial de precios |
| POST | `/api/verduras/businesses/<bid>/products/<pid>/price` | Cambio de precio con historial (`x-api-key`) |
| GET/POST | `/api/verduras/businesses/<bid>/settings` | Config del negocio: WhatsApp, abierto/cerrado, domicilio (`POST` con `x-api-key`) |
| POST | `/api/verduras/businesses/<bid>/sales` | Crear venta: delivery público (honeypot + t0 + rate limit) o walk-in POS (`x-api-key`). Idempotente con `idempotency_key` |
| GET | `/api/verduras/businesses/<bid>/sales` | Listar ventas del negocio (filtros `?status=&date_from=&date_to=`) (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/sales/<id>` | Detalle de venta con items y `whatsapp_link` (`x-api-key`) |
| POST | `/api/verduras/businesses/<bid>/sales/<id>/complete` | Marcar completada (solo desde pending) (`x-api-key`) |
| POST | `/api/verduras/businesses/<bid>/sales/<id>/cancel` | Marcar cancelada (solo desde pending) (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/inventory` | Stock derivado de todos los productos activos (compras − ventas − merma) (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/inventory/<pid>` | Stock, costo promedio y valor del stock de un producto (`x-api-key`) |
| POST/GET | `/api/verduras/businesses/<bid>/inventory/lots` | Registrar compra por lote (costo/kg derivado) o listar lotes (`x-api-key`) |
| POST/GET | `/api/verduras/businesses/<bid>/inventory/merma` | Registrar pérdida (COP congelado) o listar con filtros (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/inventory/merma/report` | Reporte semanal/mensual: pérdida por producto, % y % sobre compras (`x-api-key`) |
| GET | `/api/verduras/businesses/<bid>/inventory/alerts` | Alertas de rotación activas: severidad, días restantes, mensaje (`x-api-key`) |
| POST | `/api/verduras/businesses/<bid>/inventory/products/<pid>/min-stock` | Configurar el umbral de alerta del producto (`null` = sin alerta) (`x-api-key`) |
| POST | `/api/verduras/businesses/<bid>/pos-pin` | Configurar el PIN del POS (onboarding server-to-server, `x-api-key`) |
| GET/POST | `/pos/setup/<slug>/<token>` | **Setup con token de un solo uso** (registro self-service): el dueño elige PIN + WhatsApp; el enlace muere al usarse |
| GET | `/pos/<slug>/api/scale/weight` | Leer la báscula del POS por sesión (409 con `error_code` si falla; el manual sigue siendo la fuente de verdad) |
| GET/POST | `/pos/login` | Login del tendero (slug + PIN, sesión firmada; CSRF activo) |
| GET | `/pos/<slug>` | Dashboard POS (venta de mostrador; requiere sesión) |
| POST | `/pos/<slug>/sell` | Cobrar venta walk-in por sesión (sin x-api-key en el navegador) |
| POST | `/pos/logout` | Cerrar sesión del POS |

## Estructura

```
verduras/
├── run.py              # Entrypoint (puerto 5100)
├── settings.py         # Config propia; lee el .env de la raíz
├── app_factory.py      # create_app() del módulo
├── extensions.py       # db (la de core) + migrate propia + CSRF
├── auth.py             # x-api-key (tiempo constante), mismo patrón que core
├── models.py           # Catálogo (categorías, productos, price_history)
├── models_sales.py     # Ventas (settings, sales, sale_items, counters)
├── migrations/         # Cadena PROPIA (version_table alembic_version_verduras)
├── services/
│   ├── context.py      # Resolución/validación de tenant (punto único)
│   ├── catalog.py      # Lógica de catálogo y precios
│   ├── sales.py        # Venta por peso, idempotencia, guards, wa.me
│   ├── inventory.py    # Lotes, stock derivado, merma y reportes
│   └── pos_auth.py     # Login slug+PIN, lockout, sesión del POS
├── routes/
│   ├── health.py       # Healthchecks
│   ├── businesses.py   # API JSON de businesses del vertical
│   ├── sales.py        # API de settings y ventas (Semana 2)
│   ├── inventory.py    # API de inventario y merma (Semana 3)
│   └── dashboard.py    # Dashboard POS (login + venta por sesión)
├── templates/          # Jinja2 (pos_login, pos)
├── static/CSS|JS/      # Design system verde claro + vanilla JS
└── tests/              # Suite propia (sqlite in-memory)
```

## Roadmap (plan de producto Velzia Verduras)

| Semana | Módulo | Estado |
|--------|--------|--------|
| 1 | **Catálogo + precios por peso** (categorías, productos kg/lb/unidad, historial de precios) | ✅ Implementado |
| 2 | Ventas: venta por peso, pedidos WhatsApp (mismo patrón core), tickets | ✅ Implementado (tickets en Semana 3) |
| 3 | Inventario (compras por lote, costo/kg, stock) + **Merma** (la joya: kg dañados y pérdida en COP por producto) | ✅ Implementado (tickets comparten flujo con core) |
| 4 | Báscula digital (USB serial, protocolos `generic`/`toledo`; fallback manual de peso) | ✅ Implementado (opcional, apagada por defecto) |
| 5 | Alertas de rotación ("te quedan 3kg de banano") | ✅ Implementado (umbral opt-in por producto, badges en el POS) |
| 6 | Piloto con cliente real | ⬜ |

Notas de arquitectura del plan:
- Las tablas de ventas/inventario (semana 2-3) deben nacer capturando merma
  (kg dañados, motivo) para no perder la serie histórica del piloto.
- **Copilot VZ: ÚNICO, en core.** Este módulo se conecta por `business_id`;
  nunca construye un copiloto propio (regla en AGENTS.md).

## Dashboard POS (frontend del tendero)

**Design system propio del vertical** (diferente a Restaurantes a propósito):
claro (`#FAFAFA`), verde (`--brand-accent: #16A34A` para iconos/detalles,
`--brand: #15803D` para botones con texto blanco — contraste WCAG), estados
SIEMPRE con icono + texto (nunca solo color), mobile first con bottom-nav y
targets táctiles ≥ 56px, lenguaje de verdulero ("Registrar compra", no
"crear lote"). Tokens completos en `static/CSS/pos.css`.

**Auth:** login slug + PIN (4-6 dígitos, hash werkzeug, lockout 5 intentos
→ 10 min). El PIN vive en `verduras_business_settings` (tabla propia del
módulo) y lo configura el onboarding vía `POST .../pos-pin` con
`x-api-key` — la SERVICE_API_KEY **jamás llega al navegador**. La venta del
POS va por sesión con CSRF (guard manual en la factory, exento para
`/api/*`).

### Báscula digital (opcional, Semana 4)

Apagada por defecto; se activa por variables de entorno en el `.env` de la
raíz. Requiere `pip install pyserial` SOLO si se activa:

```bash
VERDURAS_SCALE_ENABLED=1
VERDURAS_SCALE_PORT=COM3          # o /dev/ttyUSB0 en Linux
VERDURAS_SCALE_BAUDRATE=9600
VERDURAS_SCALE_PROTOCOL=generic   # 'generic' (ASCII) | 'toledo' (frames en gramos)
VERDURAS_SCALE_TIMEOUT_S=2
```

Con la báscula activada, el POS muestra un botón "Leer báscula" junto a la
cantidad de los productos por peso (kg y lb). Si falla la lectura, el
tendero teclea el peso: la venta nunca se bloquea por la báscula.

> **Decisión de producto (piloto):** la pantalla "Configurar báscula" con
> detección automática queda DIFERIDA hasta tener la primera báscula física
> para probar. Cuando se construya, la configuración debe moverse del
> `.env` (una báscula por servidor) a **por negocio** en
> `verduras_business_settings` — cada tendero tiene SU báscula. El endpoint
> ya acepta los parámetros por llamada, así que el cambio de fuente es
> trivial.

### Suscripción (ciclo del negocio, v0.9.0)

El POS respeta el ciclo de suscripción que vive en **core** (el módulo
gestión decisiones de facturación — solo pregunta):

- Vigente o por vencer (≤ 7 días): se vende normal; el badge lo refleja.
- Gracia / vencida / dormant: `pos_view` muestra `pos_renewal.html` con el
  mensaje y un enlace de renovación hacia `{CORE_BASE_URL}/renew`, y
  `pos_sell` rechaza con 409 `suscripcion_inactiva`. Datos SIEMPRE
  preservados (misma política SaaS de core: nunca borrar).
- Businesses legacy (piloto, sin dueño ni fecha de vencimiento): **nunca**
  se bloquean — backward-compatible con el onboarding asistido.
- La renovación/pago ocurre en core (MercadoPago, `external_reference`
  `biz:<id>:<plan>`); al confirmarse, el POS vuelve a estar operativo
  sin intervención en el módulo.

Variables relevantes: `CORE_BASE_URL` (origen de core para el enlace de
renovación; default `http://localhost:5000`).

## Extracción futura a repo propio

Cuando el vertical madure, `git subtree split -P verduras` produce un repo
independiente con toda la historia. Para que sea mecánico:

- El paquete NO se llama `app/` (ese nombre es de core) y no importa nada
  de `app.*` fuera de `verduras/extensions.py` y `verduras/services/context.py`.
- Las rutas nunca importan models de core directamente: usan los services.
- Sin dependencias de rutas de core ni de sus templates.

El único cambio en la extracción será sustituir la importación de
`app.models` por el paquete publicado `velzia-core`.

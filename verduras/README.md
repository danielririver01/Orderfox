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

## Estructura

```
verduras/
├── run.py              # Entrypoint (puerto 5100)
├── settings.py         # Config propia; lee el .env de la raíz
├── app_factory.py      # create_app() del módulo
├── extensions.py       # db (la de core) + migrate propia
├── auth.py             # x-api-key (tiempo constante), mismo patrón que core
├── models.py           # Catálogo (categorías, productos, price_history)
├── models_sales.py     # Ventas (settings, sales, sale_items, counters)
├── migrations/         # Cadena PROPIA (version_table alembic_version_verduras)
├── services/
│   ├── context.py      # Resolución/validación de tenant (punto único)
│   ├── catalog.py      # Lógica de catálogo y precios
│   └── sales.py        # Venta por peso, idempotencia, guards, wa.me
├── routes/
│   ├── health.py       # Healthchecks
│   ├── businesses.py   # API JSON de businesses del vertical
│   └── sales.py        # API de settings y ventas (Semana 2)
└── tests/              # Suite propia (sqlite in-memory)
```

## Roadmap (plan de producto Velzia Verduras)

| Semana | Módulo | Estado |
|--------|--------|--------|
| 1 | **Catálogo + precios por peso** (categorías, productos kg/lb/unidad, historial de precios) | ✅ Implementado |
| 1 | **Catálogo + precios por peso** (categorías, productos kg/lb/unidad, historial de precios) | ✅ Implementado |
| 2 | Ventas: venta por peso, pedidos WhatsApp (mismo patrón core), tickets | ✅ Implementado (tickets en Semana 3) |
| 3 | Inventario (compras por lote, costo/kg, stock) + **Merma** (la joya: kg dañados y pérdida en COP por producto) | ⬜ (los tickets comparten flujo aquí) |
| 4 | Báscula digital (USB serial / Bluetooth; fallback manual de peso) | ⬜ |
| 5 | Alertas de rotación ("te quedan 3kg de banano") | ⬜ |
| 6 | Piloto con cliente real | ⬜ |

Notas de arquitectura del plan:
- Las tablas de ventas/inventario (semana 2-3) deben nacer capturando merma
  (kg dañados, motivo) para no perder la serie histórica del piloto.
- **Copilot VZ: ÚNICO, en core.** Este módulo se conecta por `business_id`;
  nunca construye un copiloto propio (regla en AGENTS.md).

## Extracción futura a repo propio

Cuando el vertical madure, `git subtree split -P verduras` produce un repo
independiente con toda la historia. Para que sea mecánico:

- El paquete NO se llama `app/` (ese nombre es de core) y no importa nada
  de `app.*` fuera de `verduras/extensions.py` y `verduras/services/context.py`.
- Las rutas nunca importan models de core directamente: usan los services.
- Sin dependencias de rutas de core ni de sus templates.

El único cambio en la extracción será sustituir la importación de
`app.models` por el paquete publicado `velzia-core`.

# 04 — Puentes (integración core ↔ módulos)

Cómo se conectan Velzia Core y los módulos sin acoplarse. El canal
principal es **la DB compartida** (`DATABASE_URL` de la raíz); todo lo
demás son convenciones encima de ella.

## DB compartida, migraciones separadas

| Cadena | Dueña de | Version table | Excluye del autogenerate |
|--------|----------|---------------|--------------------------|
| Core (`migrations/versions/`) | Todo menos `verduras_*` (`businesses` incluida) | `alembic_version` | `verduras_*` (vía `include_object` en `env.py`) |
| Módulo (`verduras/migrations/`) | Solo tablas `verduras_*` | `alembic_version_verduras` | Todo lo demás (filtro a su prefijo) |

Las dos cadenas conviven en la misma DB sin tocarse. Regla espejo: el
`env.py` de core también excluye `velzia_*` (tablas del Scanner IA externo
por Prisma) — misma clase de problema (ver VLZ-3 en Linear).

> ⚠️ Operativo: la base local de desarrollo es compartida entre ramas.
> `alembic_version` solo guarda UNA posición; al cambiar de rama
> (`main` ↔ `feature/verduras`) hay que re-estampar
> (`flask db stamp <head-de-la-rama>`). Se resuelve solo al fusionar.

## Puente Business ↔ Restaurant (`app/models/business.py`)

- `businesses.id == restaurants.id` para espejos: las FKs `restaurant_id`
  existentes siguen válidas SIN migración masiva.
- Listeners ORM (`after_insert` / `before_update` / `before_delete` sobre
  `Restaurant`) mantienen el invariante 1:1 en el mismo commit/rollback.
- **Banda reservada:** verticales directos usan IDs ≥ `1_000_000`
  (`DIRECT_VERTICAL_ID_FLOOR`); los espejos usan el autoincrement real
  (< 1M). Ambas poblaciones nunca chocan.
- ⚠️ SQL crudo (UPDATE/DELETE) contra `restaurants` bypassa el puente —
  usar ORM.
- Código NUEVO usa `Business`/`Tenant` + `business_id`; nunca crear FKs
  nuevas hacia `restaurants`.

## Tokens por la DB compartida

| Token | Emite | Consume | Vida |
|-------|-------|---------|------|
| `pos_setup_token` | Core al registrar (`register_verduras_business`) | Módulo en `/pos/setup/<slug>/<token>` (PIN + WhatsApp) | Un solo uso; muere al usarse |
| `pos_sso_token` (+ `pos_sso_expires_at`) | Core en `mundos_pos` (dueño ya verificado) | Módulo en `/pos/sso/<slug>/<token>` | Un solo uso, 5 min, solo uno vivo; comparación en tiempo constante; nunca se loguea |

## URLs cross-app

- Core → módulo: `{VERDURAS_BASE_URL}/pos/sso/<slug>/<token>` (default `http://localhost:5100`).
- Módulo → core: `{CORE_BASE_URL}/renew` para renovación (default `http://localhost:5000`).
- Pagos: MercadoPago con `external_reference` `biz:<id>:<plan>`; al confirmarse, el POS vuelve a operar sin intervención.

## Punto único de contacto (`verduras/services/context.py`)

Todo acceso del módulo a `Business` pasa por `get_business()` /
`require_business()` / `get_subscription_status()` /
`ensure_business_active()` / `list_verduras_businesses()`. Si el módulo se
extrae a repo propio, **solo ese archivo cambia** (de SQLAlchemy directo a
cliente HTTP de core). Junto con `verduras/extensions.py`, son los únicos
lugares que importan `app.*`.

## Reglas anti-duplicación (contrato del monorepo)

1. **Auth de módulo:** cada vertical tiene SU login propio (UI y
   credencial son decisión de producto) pero la lógica NO se copia.
   Referencia: `verduras/services/pos_auth.py` (PIN hasheado, lockout,
   sesión+CSRF, mensajes genéricos). Al construir el módulo #2
   EXTRAER el patrón común a `modules_common/auth.py`; el módulo #3+
   nace sobre el kit. Auth unificada (core como proveedor de identidad)
   es el horizonte final.
2. **Copilot único:** hay UN solo Copilot VZ, en core. Los submódulos
   NUNCA construyen copilotos propios; se conectan por `business_id`.
3. **Suscripción en core:** el módulo pregunta (`ensure_business_active`),
   nunca decide facturación.
4. **Alta de tenants en core:** `business_registration.py` es el único
   funnel; los módulos jamás crean tenants.
5. **Trial único:** `TrialHistory` compartido; el trial es del SaaS
   completo, no del mundo.

## Extracción futura a repo propio

Cuando el vertical madure, `git subtree split -P verduras` produce un repo
independiente con toda la historia. Condiciones (ya cumplidas):

- El paquete NO se llama `app/` y no importa `app.*` fuera de
  `extensions.py` y `services/context.py`.
- Las rutas usan services, nunca modelos de core directos.
- Sin dependencias de rutas ni templates de core.

El único cambio en la extracción será sustituir la importación de
`app.models` por el paquete publicado `velzia-core`.

# 05 — Modelo de datos (Mundos)

## `businesses` — raíz del tenant multi-vertical

Dueña: **core** (`app/models/business.py`). Los módulos la leen por la DB
compartida; nunca la migran ellos.

| Columna | Tipo | Qué es |
|---------|------|--------|
| `id` | PK int | Espejos: = `restaurants.id`. Directos: ≥ 1.000.000 |
| `vertical` | string(30) | `'restaurant'` (espejo) · `'verduras'` · futuros: delivery, farmacia… |
| `name` / `slug` | string | Nombre y slug único (URL del POS, login) |
| `is_active` | bool | Tenant operativo |
| `owner_user_id` | FK `users.id` NULL, SET NULL | Dueño (cuenta de core). Espejos: NULL (el dueño ahí es `User.restaurant_id`) |
| `plan_type` | string(20) | `trial` · `emprendedor` · `crecimiento` · `elite` |
| `subscription_expires_at` | AwareDateTime NULL | Vencimiento del tenant directo |
| `subscription_state` | string(20) | `active` · `dormant` · `cancellation_pending` (misma semántica que Restaurant) |
| `dormant_at` | AwareDateTime NULL | Auditoría del dormido (preservar, nunca borrar) |
| `has_used_trial` | bool | Anti-doble-trial por tenant |
| `whatsapp_phone` | string(20) NULL | Pedido una vez en el registro; el setup lo pre-llena |
| `pos_setup_token` | string(64) NULL | Onboarding del POS, un solo uso |
| `pos_sso_token` / `pos_sso_expires_at` | string(64) / AwareDateTime NULL | Handoff Mundos→POS, un solo uso, 5 min |
| `created_at` / `updated_at` | AwareDateTime | Auditoría |

Relación de solo lectura `restaurant_profile` (Restaurant con el mismo ID,
sin FK, escritura solo vía listeners).

## Espejos vs verticales directos

```
restaurants (id=42, slug="aji-brasa")
    │ after_insert / before_update / before_delete
    ▼
businesses (id=42, vertical='restaurant', slug="aji-brasa")   ← ESPEJO

Business.create_direct_vertical('verduras', ...)              ← DIRECTO
    ▼
businesses (id=1000000, vertical='verduras', owner, plan, trial…)
```

## Tablas `verduras_*` (dueño: el módulo)

Todas con `business_id` → FK `businesses.id`. Nunca FKs hacia `restaurants`.

| Tabla | Modelo | Qué guarda |
|-------|--------|------------|
| `verduras_categories` | `VerdurasCategory` | Categorías del negocio |
| `verduras_products` | `VerdurasProduct` | Productos (unidad kg/lb/unidad, precio actual, foto, `min_stock` opt-in) |
| `verduras_price_history` | `VerdurasPriceHistory` | Historial de cambios de precio |
| `verduras_lots` | `VerdurasLot` | Compras por lote (cantidad, costo total, costo/kg derivado, fecha) |
| `verduras_merma` | `VerdurasMerma` | Pérdidas (cantidad, motivo, costo congelado en COP, fecha) |
| `verduras_ajustes` | `VerdurasAjuste` | Ajustes manuales de stock (contado vs sistema, delta, motivo, nota) |
| `verduras_business_settings` | `VerdurasBusinessSettings` | Config: WhatsApp, abierto/cerrado, domicilio, PIN hasheado |
| `verduras_sales` | `VerdurasSale` | Ventas (número, cliente, tipo walk-in/delivery, total, estado, idempotencia, pago, `client_id` nullable) |
| `verduras_sale_items` | `VerdurasSaleItem` | Items por peso (producto, unidad, precio, cantidad, subtotal) |
| `verduras_sale_counters` | `VerdurasSaleCounter` | Consecutivo de ventas por negocio+día |
| `verduras_cierres` | `VerdurasCierre` | Cierre del día, único por día (esperado, contado, diferencia) |
| `verduras_movimientos_caja` | `VerdurasMovimientoCaja` | Libro mínimo: ingresos/retiros con motivo |
| `verduras_clientes` | `VerdurasCliente` | Clientes (nombre, teléfono, fecha de compromiso, límite) |
| `verduras_abonos` | `VerdurasAbono` | Abonos a fiados (monto, método, nota, fecha) |

Stock derivado (jamás almacenado): compras − ventas − merma ± ajustes.
Deuda de cliente (jamás almacenada): fiados − abonos.

## Tablas vecinas (no son de Mundos, pero conviven en la DB)

- `velzia_*` (`category`, `expense`, `budget`): Scanner IA externo (Prisma).
  Excluidas del autogenerate de core (ver VLZ-3).
- `alembic_version` / `alembic_version_verduras`: posiciones de cada
  cadena de migraciones (una por dueña, misma DB).

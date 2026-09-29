# 03 — Modelo de datos (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

**Método:** `[EJECUTADO]` El esquema se extrajo del metadata real de SQLAlchemy
tras crear la aplicación (`db.metadata`), no leyendo los archivos a ojo. Las
restricciones e índices citados son los que el ORM declara efectivamente.

---

## 1. Resumen

| Métrica | Valor |
|---|---|
| Tablas declaradas por los modelos | **27** |
| Tablas presentes en las migraciones pero **sin modelo** | **3** (`velzia_*`) |
| Migraciones Alembic | 31, una sola cabeza: `c0a5f7e8d9b1` |
| Entidad raíz del multi-inquilino | `restaurants` |
| Convención de nombres | `snake_case`, tablas en plural |
| Claves primarias | `INTEGER` autoincremental en las 27 tablas |
| Importes monetarios | **`INTEGER`** (pesos colombianos sin decimales) |
| Fechas | `AwareDateTime` (UTC) salvo las reservas |

---

## 2. Diagrama de relaciones

```
                              ┌──────────────┐
                              │ restaurants  │  ← raíz del inquilino
                              └──────┬───────┘
      ┌───────────────┬──────────────┼──────────────┬────────────────┐
      │               │              │              │                │
 ┌────▼────┐   ┌──────▼─────┐  ┌─────▼────┐  ┌──────▼──────┐  ┌──────▼───────┐
 │  users  │   │ categories │  │  tables  │  │   orders    │  │ reservations │
 └────┬────┘   └──────┬─────┘  └────┬─────┘  └──────┬──────┘  └──────────────┘
      │               │             │               │
      │         ┌─────▼─────┐       │      ┌────────┼─────────┐
      │         │ products  │       │      │        │         │
      │         └─────┬─────┘       │  ┌───▼────┐ ┌─▼──────┐ ┌▼─────────────┐
      │         ┌─────▼─────┐       │  │order_  │ │order_  │ │order_counters│
      │         │ modifiers │       │  │items   │ │events  │ └──────────────┘
      │         └───────────┘       │  └────────┘ └────────┘
      │                             │
      │   ┌─────────────────────────┘  (orders.table_id → SET NULL)
      │   │  (reservations.table_id → SET NULL)
      │
      ├── ai_token_wallets (1:1) ── ai_token_transactions
      ├── user_achievements
      ├── reward_claims ────────── discount_coupons
      ├── copilot_conversations ── copilot_messages
      │                        └── ai_llm_calls
      └── cash_registers (closed_by → SET NULL)

 Por restaurante, sin más hijos:
   expenses · streaks (1:1) · reservation_settings (1:1) · copilot_business_events

 Sin relación (tablas globales):
   pre_registrations · trial_history · platform_benchmarks
```

---

## 3. Entidades por dominio

### 3.1 Núcleo

#### `restaurants` — 25 columnas

`[CÓDIGO]` `app/models/core.py:40-107`. La entidad central; todo cuelga de aquí.

| Grupo | Columnas |
|---|---|
| Identidad | `id`, `name`, `slug` **(UNIQUE)**, `whatsapp_phone`, `cuisine_type` (def. `general`) |
| Marca (v1.5) | `cover_image`, `brand_color` (hex `#RRGGBB`), `estimated_time` (minutos) |
| Suscripción | `plan_type` (def. `emprendedor`), `subscription_expires_at`, `is_active` (def. **`False`**), `subscription_state` (def. `active`), `dormant_at`, `cancellation_requested_at`, `has_used_trial` |
| Operación | `is_open` (def. `True`), `pending_expiry_hours` (def. 24), `ntfy_topic` **(UNIQUE)** |
| Copilot | `copilot_analysis_depth` (def. `normal`), `copilot_notifications`, `allow_benchmark` (def. **`True`**), `web_search_enabled` (def. `False`), `web_search_queries_this_month`, `web_search_month_reset` |
| Auditoría | `created_at` |

`[CÓDIGO]` **`is_active` nace en `False`** y `subscription_state` en `'active'`:
un restaurante recién creado está simultáneamente "no activo" y en estado de
suscripción "activo". La combinación que de verdad importa la resuelve
`get_subscription_status()`.

`[CÓDIGO]` `allow_benchmark` es **opt-out**: por defecto el restaurante participa
en los benchmarks anónimos. El comentario del código cita la **Ley 1581 de 2012**
(protección de datos personales de Colombia) como justificación
(`app/models/core.py:64-66`).

#### `users` — 11 columnas

`[CÓDIGO]` `app/models/core.py:111-142`.

| Columna | Nota |
|---|---|
| `restaurant_id` | **NULLABLE** — puede existir un usuario sin restaurante (estado intermedio del alta) |
| `email` | **UNIQUE** global, no por restaurante |
| `password` | Hash de Werkzeug, **obligatorio** aunque se use Clerk |
| `clerk_id` | **UNIQUE**, indexado, nullable |
| `role` | `owner` \| `cashier` \| `waiter` (def. `owner`) |
| `pin_hash` | Solo empleados; el dueño no tiene PIN |
| `failed_pin_attempts`, `locked_until` | Anti fuerza bruta (5 intentos / 30 min) |
| `is_active` | Permite desactivar empleados sin borrarlos |

`[CÓDIGO]` **No hay restricción que impida más de un `owner` por restaurante.**
`app/utils/auth.py:106-107` toma el primero que encuentre:
`next((u for u in restaurant.users if u.role == 'owner'), None)`.

#### `categories`, `products`, `modifiers`, `tables`

| Tabla | Puntos destacados |
|---|---|
| `categories` | `sort_order` (def. 0), `is_active`, `image_url` |
| `products` | `price` **INTEGER**; distintivos `is_vegetarian`, `is_spicy`, `is_featured`; metadatos de foto automática `image_source`, `is_auto_image`, `suggested_image_pool` (JSON en texto), `unsplash_source_url` |
| `modifiers` | `extra_price` INTEGER (def. 0); **solo disponible en el plan Élite** (`has_modifiers`) |
| `tables` | `capacity` **nullable** → las reservas la tratan como 4 por defecto; `qr_code` |

`[CÓDIGO]` **No hay restricción de unicidad** en `categories.name` ni en
`products.name` por restaurante: se admiten nombres duplicados.

### 3.2 Pedidos

#### `orders` — 18 columnas

`[CÓDIGO]` `app/models/orders.py:9-47`.

| Grupo | Columnas |
|---|---|
| Identidad | `order_number` (VARCHAR 20, **sin UNIQUE**), `restaurant_id`, `table_id` (**SET NULL**) |
| Cliente | `customer_name`, `customer_phone`, `notes` |
| Estado | `status` (def. `pending`), `total` INTEGER, `expires_at` |
| Pago | `payment_method`, `amount_received`, `change_due`, `paid_at` — **todos nullable** |
| Anti-abuso | `ip_address` (indexado), `idempotency_key` |
| Auditoría | `created_at`, `updated_at` |

**Restricción clave:** `UNIQUE(restaurant_id, idempotency_key)` —
`uq_orders_restaurant_idempotency`.

`[CÓDIGO]` La unicidad del número de pedido **no la garantiza la base de datos**;
depende del contador atómico `order_counters` con
`UNIQUE(restaurant_id, date)`.

`[CÓDIGO]` `orders.table_id` usa `SET NULL` y la relación se declara **sin
cascade** para preservar el histórico si se borra la mesa
(`app/models/orders.py:44`).

#### `order_items`, `order_events`, `order_counters`

| Tabla | Notas |
|---|---|
| `order_items` | Guarda **copia** de `product_name`, `product_price` y `modifiers_snapshot` (JSON en texto). No hay FK a `products`: el histórico sobrevive al borrado del producto |
| `order_events` | Trazabilidad. El atributo Python es `event_data` pero **la columna se llama `metadata`** (`metadata` está reservado por SQLAlchemy). `actor_id` → SET NULL |
| `order_counters` | `UNIQUE(restaurant_id, date)`; numeración atómica diaria |

### 3.3 Caja

#### `cash_registers` — 18 columnas

`[CÓDIGO]` Instantánea de un cierre: `period_start` / `period_end`,
`total_sales`, `total_orders`, `avg_ticket`, desglose por método
(`cash_*`, `nequi_*`, `bancolombia_*`, `card_*`) y `cash_change_total`.

**Restricción:** `UNIQUE(restaurant_id, period_start)` — red de seguridad contra
doble cierre. `[CÓDIGO]` La regla de **no solapamiento** entre rangos la aplica
`CashRegisterService`, **no la base de datos**.

`[CÓDIGO]` `closed_by` → `users.id` con SET NULL. El docstring
(`app/models/cash.py:11-13`) advierte que hoy **cualquier usuario del
restaurante puede cerrar caja**, y que la columna existe para soportar roles más
adelante.

### 3.4 Créditos de IA

| Tabla | Descripción |
|---|---|
| `ai_token_wallets` | **1:1 con `users`** (`UNIQUE(user_id)`). `plan_limit` **NULL = Élite (ilimitado)**. `plan_tokens` (se reinician al renovar) + `extra_tokens` (comprados, no expiran) |
| `ai_token_transactions` | Log inmutable. `amount > 0` recarga, `< 0` consumo. `mp_payment_id` **UNIQUE** → idempotencia de pagos |

`[CÓDIGO]` Orden de consumo: primero `plan_tokens`, luego `extra_tokens`
(`app/models/tokens.py:16-17`).

`[CÓDIGO]` `AITokenWallet.is_elite` no lee `plan_limit`: consulta
`self.user.restaurant.plan_type == 'elite'` (`app/models/tokens.py:39-41`). Hay
por tanto **dos fuentes de verdad** de "es Élite": `plan_limit IS NULL` y
`plan_type == 'elite'`.

### 3.5 Copilot VZ

| Tabla | Descripción |
|---|---|
| `copilot_conversations` | `source` = `insights` \| `cash_register` (indexado). `prompt_version` versiona el prompt usado. `analysis_active` + `follow_up_count` implementan el tope de seguimientos gratis |
| `copilot_messages` | `role`, `content`, `metadata_json` |
| `copilot_business_events` | Eventos proactivos: `kind`, `priority`, `template_key`, `active`, `consumed_at`, `dismissed_at` |
| `ai_llm_calls` | Telemetría de coste: `input_tokens_est`, `output_tokens_est`, `execution_ms`, `source` |
| `platform_benchmarks` | Medianas anónimas por `cohort` (**UNIQUE**), con `restaurant_count` para k-anonymity |

### 3.6 Recompensas y captación

| Tabla | Descripción |
|---|---|
| `pre_registrations` | `email` **UNIQUE** + `selected_plan` |
| `trial_history` | Correos/teléfonos que **ya consumieron** la prueba gratuita. **Tabla global, sin FK**: sobrevive al borrado de la cuenta |
| `reward_claims` | `short_code` **UNIQUE** + `token` **UNIQUE** (UUID); `rarity`, `reward_type`, `status` |
| `discount_coupons` | `percentage`, `status`, `expires_at`, `applied_to_payment_id` |
| `user_achievements` | `UNIQUE(user_id, achievement_id)` |
| `streaks` | **1:1 con restaurante** (`UNIQUE`): `renewal_count`, `highest_tier` |
| `expenses` | Gastos: `description`, `amount`, `category`, `date` |

`[INFERIDO]` `expenses` parece solapar funcionalmente con `velzia_expense`, la
tabla que usa el Scanner IA externo (§5). No hay ninguna FK ni sincronización
entre ambas en este repositorio. `[PENDIENTE]` aclarar cuál es la buena.

### 3.7 Reservas

| Tabla | Descripción |
|---|---|
| `reservations` | `reservation_date` (DATE) y `reservation_time` (TIME) en **hora local de Colombia**; `party_size`, `status`, `reminder_sent`, `ip_address`; auditoría en UTC |
| `reservation_settings` | 1:1 por restaurante: `service_duration_min` (90), `cleanup_buffer_min` (15), `min_notice_hours` (2), `max_advance_days` (30), `reservations_enabled`, `reminder_enabled`, `reminder_hours_before` (2) |

`[CÓDIGO]` Fórmula de ocupación documentada en el modelo
(`app/models/reservations.py:62-66`):

```
fin de reserva = hora + service_duration_min + cleanup_buffer_min
```

---

## 4. Estados y transiciones

### 4.1 Pedido (`orders.status`)

`[CÓDIGO]` `app/services/order_service.py:206-215` — la máquina de estados es explícita:

```
pending ──► confirmed ──► delivered ──┐
   │            │                     │
   │            └──► cancelled ◄──────┘
   │                     │
   ├──► cancelled        └──► pending      (reapertura)
   └──► expired  ──► (terminal, sin salidas)
```

| Desde | Hacia |
|---|---|
| `pending` | `confirmed`, `cancelled`, `expired` |
| `confirmed` | `delivered`, `cancelled` |
| `delivered` | `cancelled` |
| `cancelled` | `pending` |
| `expired` | *(ninguno)* |

`[CÓDIGO]` `delivered → cancelled` está permitido: **un pedido ya entregado puede
cancelarse**. `[PENDIENTE]` ¿Es una regla de negocio intencional (devoluciones) o
un descuido? Ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-06).

`[CONTRADICCIÓN]` `app/utils/rate_limiter.py:25` filtra por
`status.in_(['pending', 'completed'])`, pero **`'completed'` no es un estado
válido**. Ver [R-06](06-riesgos-y-deuda-tecnica.md#r-06).

### 4.2 Suscripción (`restaurants.subscription_state`)

`[CÓDIGO]` `app/models/core.py:56-58` y `app/utils/subscription.py:184-330`.

```
active ──► cancellation_pending ──► dormant
   │                                   ▲
   └──── (vencida + gracia agotada) ───┘
```

| Estado | Significado |
|---|---|
| `active` | Normal |
| `cancellation_pending` | El usuario canceló; conserva acceso hasta el vencimiento |
| `grace_period` | Documentado en `AGENTS.md` como estado, pero **no es un valor de la columna**: la gracia se calcula con fechas |
| `dormant` | Suspendido **con todos los datos preservados** |

`[CÓDIGO]` `get_subscription_status()` devuelve además estados **calculados**, no
almacenados: `not_found`, `inactive`, `no_subscription`, `expiring_soon_neutral`
(5-7 días), `expiring_soon_warning` (2-4 días), `expiring_soon_urgent` (1 día).

`[CONTRADICCIÓN]` `GRACE_PERIOD_DAYS = 5` (`app/utils/subscription.py:96`) pero el
docstring de la función inmediatamente inferior dice *"permite el acceso durante
los **10 días** post-expiración"* (`app/utils/subscription.py:105`). Ver
[C-03](06-riesgos-y-deuda-tecnica.md#c-03).

### 4.3 Reserva (`reservations.status`)

`[CÓDIGO]` Valores reales usados en `app/services/reservation_service.py`:
`pending` → `confirmed` → `completed`, con salidas `rejected` y `no_show`.

`[CONTRADICCIÓN]` El comentario del modelo (`app/models/reservations.py:37`) los
enumera **en español**: `pendiente | confirmada | rechazada | completada | no_show`.
Los valores que se guardan son los ingleses.

### 4.4 Otros estados

| Entidad | Valores |
|---|---|
| `discount_coupons.status` | `pending` → `reserved` → `applied` / `expired` |
| `reward_claims.status` | `pending` → *(reclamado)* |
| `orders.payment_method` | `cash` \| `nequi` \| `bancolombia` \| `card` |

---

## 5. Tablas que NO pertenecen a esta aplicación

`[EJECUTADO]` `flask db check` comparó los modelos contra la cabeza de
migraciones y detectó **tres tablas creadas por las migraciones para las que no
existe ningún modelo SQLAlchemy**:

| Tabla | Columnas observadas | Origen probable |
|---|---|---|
| `velzia_category` | `id` VARCHAR(64), `name`, `userId`, `createdAt`, `updatedAt` | Prisma (Scanner IA) |
| `velzia_expense` | `id`, `amount` FLOAT, `amountConfidence`, `description`, `date`, `categoryId`, `userId`, `receiptUrl`, `ocrText`, `items`, `itemsConfidence`, … | Prisma (Scanner IA) |
| `velzia_budget` | `id`, `amount`, `categoryId`, `userId`, `month`, `year`, … | Prisma (Scanner IA) |

`[INFERIDO]` El estilo delata otra tecnología: identificadores `VARCHAR(64)`
(cuid/uuid en vez de enteros), nombres en **camelCase** (`userId`, `createdAt`)
frente al `snake_case` del resto, e importes en **FLOAT** frente al `INTEGER` que
usa toda la aplicación Flask. Encaja con el esquema Prisma del servicio
`Receipt-Scanner-AI`, que `docker-compose.yml:44` conecta a la **misma**
`DATABASE_URL`.

**Consecuencia práctica:** `flask db migrate` intentará **eliminar estas tres
tablas** en la próxima autogeneración, porque no las ve en los modelos. Ver
[R-03](06-riesgos-y-deuda-tecnica.md#r-03).

---

## 6. Desincronización entre modelos y migraciones

`[EJECUTADO]` Salida de `flask db check` sobre una base recién migrada. Además de
las tablas `velzia_*`:

| # | Diferencia detectada | Lado migración | Lado modelo |
|---|---|---|---|
| 1 | Índice de `copilot_conversations.source` | `ix_copilot_conv_source` | `ix_copilot_conversations_source` |
| 2 | Índice compuesto de `orders` | `ix_orders_restaurant_paid_at` (existe) | **no declarado** |
| 3 | Nulabilidad de `reward_claims.user_id` | **NULLABLE** | **NOT NULL** |

**Lecturas:**

- (1) Es el **mismo índice con dos nombres**: al autogenerar, Alembic propondrá
  borrar uno y crear otro sobre la misma columna.
- (2) El índice `ix_orders_restaurant_paid_at` **existe en producción** (lo creó
  la migración `b5c0d1e2f3a4`) pero el modelo no lo declara: una autogeneración
  lo **borraría**, degradando las consultas del Centro de Caja que filtran por
  `restaurant_id` + `paid_at`.
- (3) El modelo declara `user_id` como obligatorio, pero en la base real la
  columna **admite NULL**. La integridad depende hoy del código, no del esquema.

> ⚠️ Mientras persistan estas diferencias, **`flask db migrate` no es seguro**:
> generará una migración destructiva. Ver
> [R-03](06-riesgos-y-deuda-tecnica.md#r-03).

---

## 7. Integridad referencial

`[CÓDIGO]` Dos políticas de borrado, aplicadas con criterio coherente:

| Política | Dónde | Intención observada |
|---|---|---|
| `ON DELETE CASCADE` | Casi todas las FK a `restaurants` y `users` | Borrar el inquilino borra sus datos |
| `ON DELETE SET NULL` | `orders.table_id`, `reservations.table_id`, `order_events.actor_id`, `cash_registers.closed_by`, `copilot_business_events.conversation_id`, `discount_coupons.reward_claim_id`, `ai_llm_calls.conversation_id` | **Preservar el histórico** aunque desaparezca la entidad referenciada |

`[CÓDIGO]` Las relaciones que apuntan a `Table` se declaran **sin** `cascade`
precisamente para no arrastrar pedidos ni reservas
(`app/models/orders.py:44`, `app/models/reservations.py:56`).

`[CÓDIGO]` `trial_history` **no tiene FK a nada**. Es deliberado: sirve para
impedir que alguien borre su cuenta y vuelva a pedir la prueba gratuita con el
mismo correo.

---

## 8. Restricciones únicas declaradas

| Tabla | Restricción |
|---|---|
| `restaurants` | `slug`, `ntfy_topic` |
| `users` | `email`, `clerk_id` |
| `orders` | `(restaurant_id, idempotency_key)` |
| `order_counters` | `(restaurant_id, date)` |
| `cash_registers` | `(restaurant_id, period_start)` |
| `user_achievements` | `(user_id, achievement_id)` |
| `ai_token_wallets` | `user_id` |
| `ai_token_transactions` | `mp_payment_id` |
| `reward_claims` | `short_code`, `token` |
| `platform_benchmarks` | `cohort` |
| `streaks` | `restaurant_id` |
| `reservation_settings` | `restaurant_id` |
| `pre_registrations` | `email` |

`[INFERIDO]` Tres de ellas (`orders.idempotency_key`,
`ai_token_transactions.mp_payment_id`, `cash_registers.period_start`) existen
para conseguir **idempotencia a nivel de base de datos** frente a reintentos de
red y webhooks duplicados.

---

## 9. Observaciones sobre el diseño

| Observación | Evidencia | Clasificación |
|---|---|---|
| Los importes son `INTEGER` en pesos colombianos; no hay decimales ni moneda | `products.price`, `orders.total`, `cash_registers.*` | `[CÓDIGO]` |
| No existe columna de moneda: el sistema asume **solo COP** | Todo el esquema | `[INFERIDO]` |
| No hay borrado lógico general; se usa `is_active` por entidad | `restaurants`, `users`, `products`, `categories`, `tables`, `modifiers` | `[CÓDIGO]` |
| `suggested_image_pool` y `modifiers_snapshot` guardan **JSON dentro de columnas TEXT** | `app/models/core.py:183`, `app/models/orders.py:59` | `[CÓDIGO]` |
| Solo `order_events.metadata` usa un tipo `JSON` nativo | `app/models/orders.py:87` | `[CÓDIGO]` |
| No hay tabla de auditoría transversal; solo `order_events` traza un dominio | — | `[CÓDIGO]` |
| No hay índice en `orders.status` ni en `orders.created_at`, que son los filtros más usados del panel | `app/models/orders.py` | `[INFERIDO]` posible impacto en rendimiento al crecer |

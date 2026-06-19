# ARCH-02: Diagrama Entidad-Relación

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Diagrama de Relaciones

```
┌──────────────────┐       ┌──────────────────┐
│   PreRegistration│       │   Restaurant     │
│──────────────────│       │──────────────────│
│ PK id            │       │ PK id            │
│ email (UQ)       │       │ name             │
│ selected_plan    │       │ slug (UQ)        │
│ whatsapp_phone   │       │ whatsapp_phone   │
│ created_at       │       │ plan_type        │
└──────────────────┘       │ subscription_expires_at│
                           │ is_active        │
┌──────────────────┐       │ is_open          │
│   TrialHistory   │       │ has_used_trial   │
│──────────────────│       │ pending_expiry_hours│
│ PK id            │       │ created_at       │
│ email            │       └───────┬──────────┘
│ whatsapp_phone   │               │
│ created_at       │       ┌───────┴──────────────────────────────┐
└──────────────────┘       │                                      │
                           │                                      │
              ┌────────────┼────────────┬────────────┬────────────┼────────────┐
              │            │            │            │            │            │
              ▼            ▼            ▼            ▼            ▼            ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
     │   User     │ │  Category  │ │   Table    │ │   Order    │ │  Expense   │ │OrderCounter│
     │────────────│ │────────────│ │────────────│ │────────────│ │────────────│ │────────────│
     │ PK id      │ │ PK id      │ │ PK id      │ │ PK id      │ │ PK id      │ │ PK id      │
     │ restaurant │ │ restaurant │ │ restaurant │ │ restaurant │ │ restaurant │ │ restaurant │
     │   _id (FK) │ │   _id (FK) │ │   _id (FK) │ │   _id (FK) │ │   _id (FK) │ │   _id (FK) │
     │ username   │ │ name       │ │ name       │ │ table_id   │ │ description│ │ date (UQ)  │
     │ email (UQ) │ │ description│ │ qr_code    │ │   (FK)     │ │ amount     │ │ counter    │
     │ password   │ │ sort_order │ │ is_active  │ │ order_num  │ │ category   │ │            │
     │ clerk_id   │ │ is_active  │ │ created_at │ │ customer_  │ │ date       │ │            │
     │   (UQ)     │ │ image_url  │ │            │ │   name     │ │ created_at │ │            │
     └───────┬────┘ │ created_at │ └────────────┘ │ customer_  │ └────────────┘ └────────────┘
             │      │ updated_at │                │   phone    │
             │      └───────┬────┘                │ status     │
             │              │                     │ total      │
             │              │                     │ notes      │
             │              │                     │ ip_address │
             │              ▼                     │ expires_at │
             │     ┌──────────────────┐           │ created_at │
             │     │    Product       │           │ updated_at │
             │     │──────────────────│           └───────┬────┘
             │     │ PK id           │                    │
             │     │ restaurant_id   │                    │
             │     │   (FK)          │                    ▼
             │     │ category_id (FK)│           ┌──────────────────┐
             │     │ name            │           │   OrderItem      │
             │     │ description     │           │──────────────────│
             │     │ price (COP)     │           │ PK id            │
             │     │ is_active       │           │ order_id (FK)    │
             │     │ image_url       │           │ restaurant_id    │
             │     │ created_at      │           │ product_name     │
             │     │ updated_at      │           │ product_price    │
             │     └───────┬────────┘           │ quantity         │
             │             │                     │ modifiers_snap   │
             │             ▼                     │ subtotal         │
             │     ┌──────────────────┐          └──────────────────┘
             │     │   Modifier       │
             │     │──────────────────│
             │     │ PK id            │
             │     │ restaurant_id    │
             │     │   (FK)           │
             │     │ product_id (FK)  │
             │     │ name             │
             │     │ extra_price      │
             │     │ is_active        │
             │     │ created_at       │
             │     │ updated_at       │
             │     └──────────────────┘
             │
             ▼
     ┌──────────────────────────────┐
     │   AITokenWallet              │
     │──────────────────────────────│
     │ PK id                        │
     │ user_id (FK, UQ)             │
     │ plan_limit (NULL=ilimitado)  │
     │ plan_tokens                  │
     │ extra_tokens                 │
     │ tokens_used_month            │
     │ reset_at                     │
     │ created_at / updated_at      │
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │   AITokenTransaction         │
     │──────────────────────────────│
     │ PK id                        │
     │ user_id (FK)                 │
     │ type (consume/topup/...)     │
     │ amount (+/-)                 │
     │ source (scanner_ia/...)      │
     │ mp_payment_id                │
     │ description                  │
     │ created_at                   │
     └──────────────────────────────┘
```

---

## 2. Descripción de Tablas

### Restaurant
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `name` | String(100) | Nombre del restaurante |
| `slug` | String(50), Unique | Slug para URL pública |
| `whatsapp_phone` | String(20) | Teléfono de contacto |
| `plan_type` | String(20) | `emprendedor`, `crecimiento`, `elite` |
| `subscription_expires_at` | DateTime (UTC) | Fecha de expiración de suscripción |
| `is_active` | Boolean | Cuenta activa/desactivada |
| `is_open` | Boolean | Restaurante abierto/cerrado |
| `has_used_trial` | Boolean | Ya usó el trial gratuito |
| `pending_expiry_hours` | Integer | Horas para expirar pedidos (default: 24) |

### User
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `restaurant_id` | Integer, FK → restaurants.id | Dueño del restaurante (nullable) |
| `username` | String(80) | Nombre de usuario |
| `email` | String(120), Unique | Correo electrónico |
| `password` | String(255) | Hash de contraseña |
| `clerk_id` | String(100), Unique, Index | ID de Clerk OAuth |

### Category
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `restaurant_id` | Integer, FK → restaurants.id | Restaurante propietario |
| `name` | String(100) | Nombre de la categoría |
| `description` | Text | Descripción opcional |
| `sort_order` | Integer | Orden de visualización |
| `is_active` | Boolean | Categoría visible/inactiva |
| `image_url` | String(255) | URL de imagen opcional |

### Product
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `restaurant_id` | Integer, FK → restaurants.id | Restaurante propietario |
| `category_id` | Integer, FK → categories.id | Categoría del producto |
| `name` | String(100) | Nombre del producto |
| `description` | Text | Descripción opcional |
| `price` | Integer | Precio en pesos colombianos (COP) |
| `is_active` | Boolean | Producto visible/inactivo |
| `image_url` | String(255) | URL de imagen opcional |

### Modifier
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `restaurant_id` | Integer, FK → restaurants.id | Restaurante propietario |
| `product_id` | Integer, FK → products.id | Producto asociado |
| `name` | String(50) | Nombre del modificador |
| `extra_price` | Integer | Precio adicional en COP ($0 o positivo) |
| `is_active` | Boolean | Modificador activo/inactivo |

### Table
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `restaurant_id` | Integer, FK → restaurants.id | Restaurante propietario |
| `name` | String(50) | Nombre de la mesa (ej: "Mesa 1") |
| `qr_code` | String(255) | URL del QR generado |
| `is_active` | Boolean | Mesa activa/inactiva |

### Order
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `restaurant_id` | Integer, FK → restaurants.id | Restaurante |
| `table_id` | Integer, FK → tables.id (nullable) | Mesa asociada |
| `order_number` | String(20) | Número de orden visible |
| `customer_name` | String(100) | Nombre del cliente |
| `customer_phone` | String(20) | Teléfono del cliente |
| `status` | String(20) | `pending`, `confirmed`, `preparing`, `ready`, `delivered`, `cancelled`, `expired` |
| `total` | Integer | Total en COP |
| `notes` | Text | Notas del pedido |
| `ip_address` | String(45), Index | IP del cliente (rate limiting) |
| `expires_at` | DateTime (UTC) | Fecha de expiración del pedido |

### OrderItem
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `order_id` | Integer, FK → orders.id | Pedido asociado |
| `restaurant_id` | Integer, FK → restaurants.id | Restaurante |
| `product_name` | String(100) | Nombre del producto (snapshot) |
| `product_price` | Integer | Precio unitario (snapshot) |
| `quantity` | Integer | Cantidad |
| `modifiers_snapshot` | Text | JSON con modificadores seleccionados |
| `subtotal` | Integer | Subtotal (price * quantity + extras) |

### AITokenWallet
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `user_id` | Integer, FK → users.id, Unique | Usuario propietario |
| `plan_limit` | Integer, nullable | Límite mensual del plan (NULL = Elite ilimitado) |
| `plan_tokens` | Integer | Tokens restantes del plan mensual |
| `extra_tokens` | Integer | Tokens comprados (no expiran) |
| `tokens_used_month` | Integer | Contador de uso mensual |
| `reset_at` | DateTime (UTC) | Próximo reset de tokens |

### AITokenTransaction
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | Integer, PK | Identificador único |
| `user_id` | Integer, FK → users.id | Usuario |
| `type` | String(20) | `consume`, `topup_plan`, `topup_purchase`, `elite_scan` |
| `amount` | Integer | Positivo = recarga, Negativo = consumo |
| `source` | String(50) | `scanner_ia`, `plan_renewal`, `mp_purchase`, `migration_seed` |
| `mp_payment_id` | String(100), nullable | ID de pago de Mercado Pago (anti-duplicado) |

---

## 3. Reglas de Integridad

| Relación | Tipo | Comportamiento en Eliminación |
|----------|------|-------------------------------|
| Restaurant → User | 1:N | CASCADE |
| Restaurant → Category | 1:N | CASCADE |
| Restaurant → Product | 1:N | CASCADE |
| Restaurant → Table | 1:N | CASCADE |
| Restaurant → Order | 1:N | CASCADE |
| Restaurant → Expense | 1:N | CASCADE |
| Category → Product | 1:N | CASCADE |
| Product → Modifier | 1:N | CASCADE |
| Table → Order | 1:N | SET NULL (preserva historial) |
| Order → OrderItem | 1:N | CASCADE |
| User → AITokenWallet | 1:1 | CASCADE |
| User → AITokenTransaction | 1:N | CASCADE |

---

## 4. Convenciones

- **Timestamps**: `created_at` y `updated_at` en todas las tablas principales
- **Tipo AwareDateTime**: Convierte UTC ↔ naive automáticamente (ver GUIDE-01)
- **snake_case**: Todos los nombres de tablas y columnas
- **Moneda**: Precios en pesos colombianos (COP), enteros
- **Soft delete**: Uso de `is_active` booleano en vez de DELETE físico (categorías, productos, modificadores, mesas)

---

## 5. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |

# Referencia de API — Velzia

> **Base URL (Flask):** `http://localhost:5000`  
> **Base URL (Next.js):** `http://localhost:3000`  
> **Formato respuesta:** JSON `{ success, message, data }` o `{ success, error_code, message }`

## Formato General

### Respuesta Exitosa
```json
{
  "success": true,
  "message": "Operación exitosa",
  "data": { }
}
```

### Respuesta Error
```json
{
  "success": false,
  "error_code": "ERROR_CODE",
  "message": "Descripción del error en español"
}
```

### Autenticación
| Tipo | Header | Dónde |
|------|--------|-------|
| JWT | `Authorization: Bearer <token>` | APIs móviles |
| Session | Cookie | Web dashboard |
| API Key | `x-api-key: <key>` | Server-to-server (Scanner IA) |

---

## Índice de Endpoints

### Web (HTML) — Flask

| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET/POST | `/` | No | Login |
| GET | `/register` | No | Registro |
| GET/POST | `/setup-account` | Session | Setup de cuenta |
| GET/POST | `/payment` | Session | Pago Mercado Pago |
| GET | `/planes` | No | Planes y precios |
| GET | `/dashboard/` | Session | Dashboard principal |
| GET | `/dashboard/subscription` | Session | Gestión suscripción |
| GET | `/dashboard/Productos` | Session | Productos |
| GET | `/categories/` | Session | Lista categorías |
| GET | `/categories/create` | Session | Crear categoría |
| GET | `/products/` | Session | Lista productos |
| GET | `/products/create` | Session | Crear producto |
| GET | `/orders/` | Session | Lista pedidos |
| GET | `/orders/<id>` | Session | Detalle pedido |
| GET | `/orders/<id>/receipt` | Session | Vista imprimir recibo |
| GET | `/dashboard/tables/` | Session | Gestión mesas |
| GET | `/dashboard/settings` | Session | Configuración |
| GET | `/dashboard/profile` | Session | Perfil |
| GET | `/menu/<slug>` | No | Menú público (QR) |
| GET | `/dashboard/ai-scan` | Session | Redirect a Scanner IA |

### API (JSON) — Flask

#### Auth
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| POST | `/api/auth/login` | No | Login JWT |
| POST | `/api/auth/register` | No | Pre-registro (envía OTP) |
| POST | `/api/auth/verify-otp` | No | Verifica OTP |
| POST | `/api/auth/setup-account` | Token | Completa registro |
| POST | `/api/auth/refresh` | No | Refresca JWT |
| POST | `/api/auth/logout` | No | Logout |
| GET | `/api/auth/plans` | No | Lista planes |
| POST | `/api/auth/payment/initiate` | JWT | Inicia pago MP |
| POST | `/api/auth/forgot-password` | No | Solicita reset |
| POST | `/api/auth/reset-password` | No | Reset con token |

#### Dashboard
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/dashboard/overview` | JWT | Vista general + stats hoy |
| POST | `/api/dashboard/toggle-status` | JWT | Abrir/cerrar restaurante |
| GET | `/api/dashboard/check-orders` | JWT | Polling de pedidos |
| GET | `/api/dashboard/stats` | JWT | Estadísticas por rango |
| GET | `/api/dashboard/settings` | JWT | Configuración |
| GET | `/api/dashboard/subscription` | JWT | Estado suscripción |
| PUT | `/api/dashboard/profile` | JWT | Actualizar perfil |
| POST | `/api/dashboard/delete-account` | JWT | Eliminar cuenta |
| POST | `/api/dashboard/ai-scan/token` | JWT | Token para Scanner IA |

#### Categorías
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/categories` | Dual | Lista categorías |
| POST | `/api/categories` | Dual | Crear (multipart) |
| GET | `/api/categories/<id>` | Dual | Detalle |
| PUT | `/api/categories/<id>` | Dual | Actualizar (multipart) |
| DELETE | `/api/categories/<id>` | Dual | Eliminar |
| PATCH | `/api/categories/<id>/toggle` | Dual | Activar/desactivar |
| PATCH | `/api/categories/<id>/reorder` | Dual | Reordenar |

#### Productos
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/products` | JWT | Lista (filtros: category_id, active_only, page, per_page) |
| GET | `/api/products/<id>` | JWT | Detalle + modifiers |
| POST | `/api/products` | JWT | Crear (multipart) |
| PUT | `/api/products/<id>` | JWT | Actualizar (multipart) |
| DELETE | `/api/products/<id>` | JWT | Eliminar |
| PATCH | `/api/products/<id>/toggle` | JWT | Activar/desactivar |
| GET | `/api/products/<id>/modifiers` | JWT | Modifiers del producto |
| POST | `/api/products/<id>/modifiers` | JWT | Crear modifier |
| PATCH | `/api/products/modifiers/<id>/toggle` | JWT | Toggle modifier |
| DELETE | `/api/products/modifiers/<id>` | JWT | Eliminar modifier |

#### Pedidos
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/orders` | JWT | Lista (filtros: status, sort, page) |
| GET | `/api/orders/<id>` | JWT | Detalle + items |
| POST | `/api/orders` | JWT | Crear pedido |
| PATCH | `/api/orders/<id>/status` | JWT | Cambiar estado |
| POST | `/api/orders/<id>/cancel` | JWT | Cancelar |
| GET | `/api/orders/<id>/receipt` | JWT | Datos recibo |
| DELETE | `/api/orders/<id>` | JWT | Eliminar (solo cancelled) |

#### Menú Público (sin auth)
| Método | URL | Descripción |
|--------|-----|-------------|
| GET | `/api/public/menu/<slug>` | Menú completo (cat + prod + modifiers) |
| GET | `/api/public/menu/<slug>/categoria/<id>` | Categoría + productos |
| GET | `/api/public/menu/<slug>/novedades` | Novedades (paginado) |
| GET | `/menu/<slug>/search-products` | Lista plana productos activos |
| GET | `/menu/<slug>/search` | Búsqueda textual `?q=` |

#### Mesas
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/tables` | JWT | Lista + active_orders_count |
| POST | `/api/tables` | JWT | Crear con QR |
| DELETE | `/api/tables/<id>` | JWT | Eliminar |

#### Tokens AI
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/tokens/status` | Session/JWT/Key | Estado wallet |
| POST | `/api/tokens/consume` | Session/JWT/Key | Consumir 1 token |
| POST | `/api/tokens/topup/initiate` | Session/JWT | Iniciar recarga MP |
| GET | `/api/tokens/topup/callback` | No | Callback recarga MP |

### API (JSON) — Next.js (Scanner IA)

| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| GET | `/api/test` | No | Health check |
| POST | `/api/auth/flask-token` | No | Verifica JWT de Flask |
| POST | `/api/checkout` | Clerk | Inicia pago tokens MP (proxy a Flask) |
| GET | `/api/tokens/status` | Clerk | Estado wallet tokens |
| GET | `/api/stats/summary` | API Key/Clerk | Estadísticas gastos |
| GET | `/api/export` | Clerk | Export CSV gastos |
| GET | `/stats` | Clerk | Total gastos |

---

## Endpoints Clave — Ejemplos

### `POST /api/auth/login`
```json
// Request
{ "email": "admin@restaurante.com", "password": "MiPass123" }

// Response 200
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "user": { "id": 1, "username": "admin", "email": "admin@restaurante.com" },
    "restaurant": { "id": 1, "name": "Mi Restaurante", "slug": "mi-restaurante", "plan_type": "emprendedor" }
  }
}
```

### `POST /api/orders`
```json
// Request
{
  "items": [
    { "product_id": 1, "quantity": 2, "modifiers": [{"id": 3}, {"id": 5}] },
    { "product_id": 4, "quantity": 1, "modifiers": [] }
  ],
  "customer_name": "Juan Pérez",
  "customer_phone": "3001234567",
  "table_id": 2,
  "notes": "Sin cebolla por favor"
}

// Response 201
{
  "success": true,
  "data": {
    "order_id": 45,
    "order_number": "ORD-012",
    "total": 45000,
    "status": "pending",
    "items": [
      { "product_name": "Hamburguesa Clásica", "quantity": 2, "subtotal": 24000, "modifiers": ["Extra queso"] },
      { "product_name": "Papas Fritas", "quantity": 1, "subtotal": 8000 }
    ]
  }
}
```

### `GET /api/public/menu/<slug>`
```json
{
  "success": true,
  "data": {
    "restaurant": { "name": "Pizza Roma", "slug": "pizza-roma", "is_open": true },
    "categories": [
      {
        "id": 1, "name": "Hamburguesas", "sort_order": 0,
        "products": [
          {
            "id": 1, "name": "Clásica", "price": 12000, "description": "Carne 200gr + lechuga + tomate",
            "image_url": "https://res.cloudinary.com/...", "is_active": true,
            "modifiers": [
              { "id": 1, "name": "Queso extra", "extra_price": 2000 },
              { "id": 2, "name": "Tocino", "extra_price": 3000 }
            ]
          }
        ]
      }
    ]
  }
}
```

### `GET /api/dashboard/overview`
```json
{
  "success": true,
  "data": {
    "restaurant": { "name": "Mi Restaurante", "is_open": true, "slug": "mi-rest" },
    "today": {
      "pending_orders": 3,
      "confirmed_orders": 5,
      "completed_orders": 12,
      "today_sales": 285000
    },
    "subscription": {
      "status": "active", "plan": "emprendedor", "days_remaining": 22,
      "can_crud": true
    }
  }
}
```

### `POST /api/tokens/consume`
```json
// Request (Header: x-api-key: <key>)
// Body: { "clerk_id": "user_2aBcDeFgHiJkLmNoPqRsTuVwX" }

// Response 200
{ "success": true, "tokens_remaining": 14 }

// Response 402
{ "success": false, "error_code": "INSUFFICIENT_TOKENS", "message": "No tienes tokens disponibles. Recarga en el dashboard." }
```

---

## Status Codes

| Código | Significado |
|--------|-------------|
| 200 | OK |
| 201 | Creado (POST orders) |
| 400 | Bad Request (validación) |
| 401 | No autenticado |
| 402 | Tokens insuficientes |
| 403 | Prohibido (plan no incluye feature) |
| 404 | No encontrado |
| 429 | Rate limit excedido |
| 500 | Error interno |

## Códigos de Error

| Código | Significado |
|--------|-------------|
| `USER_NOT_REGISTERED` | Usuario autenticado en Clerk pero sin registro en BD |
| `INSUFFICIENT_TOKENS` | No hay tokens disponibles para escanear |
| `PLAN_LIMIT_REACHED` | Límite de productos del plan alcanzado |
| `INVALID_STATUS_TRANSITION` | Transición de estado de pedido no válida |
| `RATE_LIMIT_BLOCKED` | IP bloqueada por spam (10 min) |
| `SUBSCRIPTION_EXPIRED` | Suscripción vencida, período de gracia |
| `FEATURE_NOT_AVAILABLE` | El plan no incluye esta funcionalidad |

---

*Documento mantenido en /docs/API_REFERENCE.md*

# GUIDE-03: Referencia de la API REST

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Formato General

Todas las respuestas JSON siguen esta estructura:

### Éxito
```json
{
  "success": true,
  "message": "Operación exitosa",
  "data": { /* payload */ }
}
```

### Error
```json
{
  "success": false,
  "error_code": "ERROR_CODE",
  "message": "Mensaje legible en español"
}
```

---

## 2. Autenticación

| Tipo | Header | Uso |
|------|--------|-----|
| Service API Key | `x-api-key: <key>` | Server-to-server (bypasea rate limiting) |
| JWT | `Authorization: Bearer <token>` | Clientes móviles/externos (24h expiración) |
| Clerk Session | Cookie | Navegador web |

---

## 3. Endpoints

### 3.1 Autenticación

#### POST /api/auth/login

Inicio de sesión tradicional (email + password).

```
Content-Type: application/json

{
  "email": "usuario@ejemplo.com",
  "password": "contraseña123"
}
```

**Respuesta 200:**
```json
{
  "success": true,
  "message": "Inicio de sesión exitoso",
  "data": {
    "user": {
      "id": 1,
      "username": "usuario",
      "email": "usuario@ejemplo.com"
    },
    "restaurant": {
      "id": 1,
      "name": "Mi Restaurante",
      "slug": "mi-restaurante"
    }
  }
}
```

**Respuesta 401:**
```json
{
  "success": false,
  "error_code": "INVALID_CREDENTIALS",
  "message": "Email o contraseña incorrectos"
}
```

---

#### POST /api/auth/sync-clerk

Sincronización de usuario desde Clerk OAuth.

```
Content-Type: application/json

{
  "clerk_id": "user_2abc123def456",
  "email": "usuario@ejemplo.com",
  "username": "usuario",
  "name": "Usuario Ejemplo"
}
```

**Respuesta 200 (usuario existente):**
```json
{
  "success": true,
  "message": "Sesión iniciada",
  "data": {
    "user": { "id": 1, "clerk_id": "user_2abc123def456", "username": "usuario" },
    "restaurant": { "id": 1, "name": "Mi Restaurante", "slug": "mi-restaurante" }
  }
}
```

**Respuesta 201 (nuevo usuario + trial):**
```json
{
  "success": true,
  "message": "Cuenta creada. Configura tu restaurante.",
  "data": {
    "user": { "id": 2, "clerk_id": "user_2abc123def456", "username": "usuario" },
    "setup_required": true
  }
}
```

**Respuesta 409 (trial ya usado):**
```json
{
  "success": false,
  "error_code": "TRIAL_ALREADY_USED",
  "message": "Este email ya ha utilizado el período de prueba"
}
```

---

### 3.2 Productos

#### GET /api/products/list

Lista todos los productos activos de un restaurante.

**Query params:** `?restaurant_slug=mi-restaurante`

**Respuesta 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Hamburguesa Clásica",
      "description": "Carne 200g, queso, lechuga, tomate",
      "price": 15000,
      "category_id": 1,
      "category_name": "Hamburguesas",
      "image_url": "https://res.cloudinary.com/...",
      "modifiers": [
        { "id": 1, "name": "Queso extra", "extra_price": 2000 },
        { "id": 2, "name": "Tocino", "extra_price": 3000 }
      ]
    }
  ]
}
```

#### POST /api/products/create

Crear un nuevo producto.

```
Content-Type: application/json

{
  "name": "Nuevo Producto",
  "description": "Descripción opcional",
  "price": 20000,
  "category_id": 1,
  "is_active": true
}
```

#### PUT /api/products/update/<id>

Actualizar un producto existente.

```
Content-Type: application/json

{
  "name": "Producto Actualizado",
  "price": 25000,
  "is_active": false
}
```

#### DELETE /api/products/delete/<id>

Eliminar un producto.

**Respuesta 200:**
```json
{
  "success": true,
  "message": "Producto eliminado correctamente"
}
```

---

### 3.3 Pedidos

#### POST /api/orders/create

Crear un nuevo pedido desde el menú público.

```
Content-Type: application/json

{
  "restaurant_id": 1,
  "table_id": 3,
  "customer_name": "Cliente Ejemplo",
  "customer_phone": "3001234567",
  "notes": "Sin cebolla",
  "cart": [
    {
      "product_id": 1,
      "product_name": "Hamburguesa Clásica",
      "product_price": 15000,
      "quantity": 2,
      "modifiers": [
        { "id": 1, "name": "Queso extra", "extra_price": 2000 }
      ]
    }
  ],
  "total": 34000
}
```

**Rate limiting:** Mínimo 12 segundos entre pedidos (30s si patrón sospechoso).

**Respuesta 201:**
```json
{
  "success": true,
  "message": "Pedido creado exitosamente",
  "data": {
    "order_id": 42,
    "order_number": "ORD-001",
    "total": 34000,
    "status": "pending",
    "estimated_wait": 20
  }
}
```

**Respuesta 429 (rate limit):**
```json
{
  "success": false,
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Por favor espera 12 segundos antes de hacer otro pedido.",
  "retry_after": 12
}
```

---

#### GET /api/orders/list

Lista de pedidos del restaurante.

**Query params:**
- `?status=pending` — filtrar por estado
- `?date=2026-06-16` — filtrar por fecha

**Respuesta 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": 42,
      "order_number": "ORD-001",
      "customer_name": "Cliente Ejemplo",
      "status": "pending",
      "total": 34000,
      "items": [
        { "product_name": "Hamburguesa Clásica", "quantity": 2, "subtotal": 34000 }
      ],
      "created_at": "2026-06-16T20:30:00+00:00"
    }
  ]
}
```

---

### 3.4 Categorías

#### GET /api/categories/list

Lista todas las categorías activas.

**Query params:** `?restaurant_slug=mi-restaurante`

**Respuesta 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Hamburguesas",
      "description": "Nuestras mejores hamburguesas",
      "sort_order": 1,
      "products_count": 5
    }
  ]
}
```

#### POST /api/categories/create

Crear categoría. Misma estructura que productos.

---

### 3.5 Tokens AI

#### GET /api/tokens/status

Estado del wallet de tokens del usuario autenticado.

**Header:** `Authorization: Bearer <jwt>`

**Respuesta 200:**
```json
{
  "success": true,
  "data": {
    "is_elite": false,
    "plan_limit": 100,
    "plan_tokens": 85,
    "extra_tokens": 15,
    "total_available": 100,
    "usage_percent": 15.0,
    "can_scan": true,
    "reset_at": "2026-07-01T00:00:00+00:00"
  }
}
```

#### POST /api/tokens/consume

Consumir un token (uso interno Scanner IA).

```
Header: Authorization: Bearer <jwt>
Content-Type: application/json

{
  "amount": 1,
  "description": "Escaneo de menú #123"
}
```

**Respuesta 200:**
```json
{
  "success": true,
  "message": "Token consumido",
  "data": {
    "remaining_tokens": 99
  }
}
```

---

### 3.6 Tablas

#### GET /api/tables/list

**Query params:** `?restaurant_slug=mi-restaurante`

```json
{
  "success": true,
  "data": [
    { "id": 1, "name": "Mesa 1", "qr_code": "https://tudominio.com/mi-restaurante/menu?mesa=1", "is_active": true }
  ]
}
```

#### POST /api/tables/create

```json
{
  "name": "Mesa 5",
  "is_active": true
}
```

---

### 3.7 Público / Menú

#### GET /api/public/menu/<slug>

Menú público del restaurante (sin autenticación).

**Respuesta 200:**
```json
{
  "success": true,
  "data": {
    "restaurant": {
      "name": "Mi Restaurante",
      "slug": "mi-restaurante",
      "is_open": true
    },
    "categories": [
      {
        "id": 1,
        "name": "Hamburguesas",
        "products": [ /* ... */ ]
      }
    ]
  }
}
```

---

## 4. Códigos de Error Globales

| Código | HTTP | Causa |
|--------|------|-------|
| `USER_NOT_REGISTERED` | 401 | JWT válido pero usuario no existe en BD |
| `SUBSCRIPTION_EXPIRED` | 403 | Suscripción vencida |
| `GRACE_PERIOD` | 403 | En período de gracia (solo lectura) |
| `FEATURE_NOT_AVAILABLE` | 403 | El plan no incluye la funcionalidad |
| `TOKEN_INSUFFICIENT` | 402 | Sin tokens AI disponibles |
| `INVALID_CREDENTIALS` | 401 | Email o contraseña incorrectos |
| `TRIAL_ALREADY_USED` | 409 | Email/whatsapp ya usó el trial |
| `RATE_LIMIT_EXCEEDED` | 429 | Demasiados pedidos en poco tiempo |
| `VALIDATION_ERROR` | 422 | Datos de entrada inválidos |
| `NOT_FOUND` | 404 | Recurso no encontrado |

---

## 5. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |

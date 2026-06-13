# Rediseño del Menú Público — Orderfox/Velzia

> Inspirado en UberEats, con identidad de marca Velzia (color primario `#f2460d`)
> Versión 2.0 — Feature flag: `?v2=true`

---

## 1. Arquitectura

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                        Navegador                            │
├─────────────────────────────────────────────────────────────┤
│  public_base.html (layout base)                             │
│  ├── api-client.js      → fetch wrapper con CSRF            │
│  ├── toast.js           → showToast() global                │
│  ├── cart.js            → loadCart/saveCart/updateQty/etc.  │
│  ├── interactions.js    → deep-link / back-to-top           │
│  ├── cart_drawer.html   → drawer deslizante (mobile)        │
│  │                                                          │
│  └── menu_public_v2.html (EXTIENDE public_base.html)        │
│       ├── menu-init.js        → entry point                 │
│       ├── menu-state.js       → estado global               │
│       ├── menu-navigation.js  → navegación por categorías   │
│       ├── menu-search.js      → búsqueda inline             │
│       ├── menu-detail.js      → bottom sheet / modal        │
│       └── menu-checkout.js    → formulario + envío          │
├─────────────────────────────────────────────────────────────┤
│                       Servidor (Flask)                       │
│  public.py → /menu/<slug> → render template                │
│  public_menu_service.py → lógica de negocio                 │
│  models.py → Restaurant, Category, Product, Modifier        │
└─────────────────────────────────────────────────────────────┘
```

### Flujo de Datos

```
1. QR escanea → /menu/<slug>?v2=true
2. Servidor renderiza categorías + productos con Jinja2
3. Browser carga HTML con data-* attributes en cada producto
4. JS lee data-* attributes (NO fetch desde API)
5. Carrito se gestiona vía localStorage (cart.js)
6. Checkout POST a /menu/api/order via apiFetch (api-client.js)
7. Éxito → muestra modal + redirección WhatsApp
```

### Principio: Server-Rendered, Client-Enhanced

- **Servidor**: renderiza HTML completo con Jinja2 (categorías, productos, modificadores)
- **Cliente**: solo lectura de `data-*` attributes para interactividad
- **Sin API calls para el menú**: cero llamadas fetch para cargar productos
- **Carrito**: única fuente de verdad es `cart.js` → localStorage

---

## 2. Componentes (Módulos JS)

| Módulo | Archivo | Responsabilidad |
|--------|---------|----------------|
| **Entry point** | `menu-init.js` | Importa todos los módulos, inicializa en DOMContentLoaded |
| **Estado** | `menu-state.js` | Expone restaurantId, slug, isTableOrder, businessPhone |
| **Navegación** | `menu-navigation.js` | Scroll spy, highlight categoría activa, sidebar/pills |
| **Búsqueda** | `menu-search.js` | Filtro inline, oculta/muestra productos, mensaje "sin resultados" |
| **Detalle** | `menu-detail.js` | Bottom sheet (mobile) / modal (desktop), modificadores, cantidad |
| **Checkout** | `menu-checkout.js` | Formulario en carrito, validación, timer anti-spam, POST |

### Dependencias Externas (no-module, cargadas por public_base.html)

- `cart.js` — `window.loadCart()`, `saveCart()`, `updateQty()`, `toggleCart()`, `clearCart()`, `updateDisplay()`, `sendWhatsApp()`
- `toast.js` — `window.showToast(message, type)`
- `api-client.js` — `window.apiFetch(url, options)`

### Template Includes (desde el servidor)

| Include | Propósito |
|---------|-----------|
| `public_base.html` | Layout base (head, scripts, cart_drawer, modals) |
| `components/cart_drawer.html` | Drawer deslizante del carrito |
| `menu_public_v2.html` | El template principal del menú v2 |

---

## 3. Estados

### Loading
- No aplica (el HTML se sirve completo del servidor)
- Las imágenes tienen `loading="lazy"` para carga progresiva

### Empty
- **Sin categorías**: mensaje "Este restaurante aún no tiene productos en su menú"
- **Sin productos en categoría**: no se renderiza la sección
- **Sin resultados de búsqueda**: mensaje "No encontramos productos con ese nombre"

### Error
- **Restaurante no encontrado**: servidor devuelve 404 (abort)
- **Pedido fallido**: `showToast('mensaje', 'error')` con el mensaje del servidor
- **Rate limiting**: `showToast('mensaje (Xs)', 'warning')` con retry_after

### Closed Restaurant
- **Local cerrado por dueño**: servidor renderiza `store_closed.html` (sin cambios)
- **Pedidos desactivados** (suscripción): `ordering_disabled = True`
  - Banner informativo en el menú
  - Botones "+" deshabilitados/ocultos
  - Se puede ver el menú pero no pedir

### Checkout States
- **Formulario abierto**: se muestra el formulario de checkout
- **Timer anti-spam**: botón deshabilitado 3 segundos con countdown
- **Enviando**: botón con spinner "Procesando..."
- **Éxito**: modal de éxito → redirección WhatsApp
- **Error**: toast con mensaje de error

---

## 4. Responsive Breakpoints

| Breakpoint | Ancho | Layout | Categorías | Carrito |
|------------|-------|--------|------------|---------|
| **Mobile** | < 768px | 1 columna | Pills horizontales (sticky) | Floating button + drawer |
| **Tablet** | 768-1024px | 2 columnas | Sidebar colapsable + pills | Drawer lateral |
| **Desktop** | > 1024px | 3 columnas `[200px 1fr 320px]` | Sidebar fija izquierda | Carrito visible derecha |

### Mobile-first Strategy

```
Base (mobile):    [categorías horizontal scroll]
                  [grid productos 2 columnas]
                  [floating cart button]

Tablet:           [sidebar categorías] [grid productos]
                  → cart drawer desde derecha

Desktop:          [sidebar 200px] [grid 1fr] [cart 320px]
                  → carrito siempre visible
```

---

## 5. Contrato de Datos

### Lo que el backend provee (Jinja2)

```python
restaurant = {
    'id': int,
    'name': str,
    'slug': str,
    'whatsapp_phone': str,
    'is_open': bool,
    'is_active': bool,
}

categories = [{
    'id': int,
    'name': str,
    'image_url': str|None,
    'active_product_count': int,
    'products': [{
        'id': int,
        'name': str,
        'description': str|None,
        'price': int,           # en pesos (ej: 15000)
        'image_url': str|None,
        'modifiers': [{         # solo activos
            'id': int,
            'name': str,
            'extra_price': int
        }]
    }]
}]

ordering_disabled = bool
```

### Lo que el template expone en data-* attributes

```html
<article data-id="123"
         data-name="Hamburguesa Clásica"
         data-price="15000"
         data-image="/static/uploads/hamburguesa.jpg"
         data-description="Carne 200g, queso, lechuga"
         data-modifiers='[{"id":1,"name":"Extra queso","extra_price":2000}]'>
```

### Lo que el frontend envía al backend

**POST** `/menu/api/order`

```json
{
    "cart": {
        "123": {
            "quantity": 2,
            "extras": [{"id": 1, "name": "Extra queso", "price": 2000}]
        }
    },
    "total": 34000,
    "restaurant_id": 1,
    "customer_name": "Juan Pérez",
    "customer_phone": "3001234567",
    "city": "Bogotá",
    "address": "Calle 123 #45-67",
    "notes": "Sin cebolla",
    "user_secondary_email": ""        // honeypot anti-bot
}
```

### Lo que el backend responde

**Éxito:**
```json
{
    "success": true,
    "order_number": "ORD-042",
    "order_id": 42,
    "total": 34000,
    "items": [{"name": "Hamburguesa Clásica", "qty": 2, "extras": ["Extra queso"]}],
    "customer_name": "Juan Pérez",
    "address_full": "Calle 123 #45-67, Bogotá",
    "table_name": null
}
```

**Error:**
```json
{
    "success": false,
    "error_code": "RATE_LIMITED",
    "message": "Debes esperar 12 segundos entre pedidos",
    "retry_after": 12
}
```

---

## 6. CART_KEY — Compatibilidad con Carritos Existentes

### Estrategia

La clave del carrito en localStorage **debe ser idéntica** entre la versión actual y la v2 para que los carritos existentes no se pierdan al activar `?v2=true`.

### Definición actual (en `public_base.html`)

```js
window.CART_KEY = `velziaCart_${window.restaurantId}`;
```

### Uso en `cart.js`

```js
const CART_KEY = window.CART_KEY || `velziaCart_${window.restaurantId || 'default'}`;
```

### Cómo se asegura en v2

1. `public_base.html` (sin cambios) define `window.CART_KEY`
2. `cart.js` (sin cambios) lee esa variable
3. Los módulos v2 **no definen su propia key** — llaman a `cart.js` functions:
   - `loadCart()` para leer el carrito
   - `saveCart()` para persistir
   - `updateQty()` para modificar cantidades
4. No hay código duplicado de gestión de carrito en v2

### Impacto

| Escenario | Comportamiento |
|-----------|---------------|
| Usuario con carrito en v1, abre v2 | Carrito preservado (misma key) |
| Usuario con carrito en v2, vuelve a v1 | Carrito preservado |
| Carrito expirado (>24h) | `cart.js` lo limpia automáticamente (TTL check) |

### Verificación

```js
// En cualquier módulo v2:
const cart = loadCart();           // viene de cart.js
console.log(CART_KEY);             // "velziaCart_<id>"
```

---

## 7. Archivos del Sistema

### Creados

| Archivo | Propósito |
|---------|-----------|
| `docs/menu-redesign.md` | Este documento de diseño |
| `app/template/public/menu_public_v2.html` | Template v2 del menú público |
| `app/static/js/public/menu-state.js` | Estado global (ES module) |
| `app/static/js/public/menu-navigation.js` | Navegación categorías (ES module) |
| `app/static/js/public/menu-search.js` | Búsqueda inline (ES module) |
| `app/static/js/public/menu-detail.js` | Detalle producto (ES module) |
| `app/static/js/public/menu-checkout.js` | Checkout (ES module) |
| `app/static/js/public/menu-init.js` | Entry point (ES module) |

### Modificados

| Archivo | Cambio |
|---------|--------|
| `app/routes/public.py` | Feature flag `?v2=true` → renderiza `menu_public_v2.html` |

### No tocados (intencionalmente)

| Archivo | Razón |
|---------|-------|
| `app/template/public/menu_public.html` | Versión actual, se mantiene hasta validar v2 |
| `app/static/js/public/menu-public.js` | Monolito actual, se mantiene |
| `app/static/CSS/public/menu_public.css` | CSS actual, se mantiene |
| `app/static/js/cart.js` | Fuente de verdad del carrito |
| `app/static/js/toast.js` | Sistema de notificaciones |
| `app/static/js/api-client.js` | Cliente HTTP |
| `app/template/components/cart_drawer.html` | Drawer compartido |
| `app/routes/menu.py` | API endpoints (sin cambios) |
| `app/services/public_menu_service.py` | Lógica de negocio |
| `app/models.py` | Modelos |

---

## 8. Riesgos e Issues

### Riesgo: Productos sin imagen
- **Issue**: El grid se ve desbalanceado si algunos productos tienen imagen y otros no
- **Mitigación**: Fallback con inicial del producto + icono comida en fondo tenue

### Riesgo: Modificadores con JSON escapado
- **Issue**: Los `data-modifiers` contienen JSON string escapado que puede romperse con caracteres especiales
- **Mitigación**: Usar `|e` (escape) en Jinja2 para nombres, `|tojson` para el array completo

### Riesgo: Carrito drawer y columna derecha en desktop
- **Issue**: El `cart_drawer.html` usa `fixed` positioning, conflictúa con la columna inline de desktop
- **Mitigación**: En desktop (>1024px) se oculta el drawer deslizante y se muestra contenido inline

### Riesgo: ES Modules y CORS en desarrollo
- **Issue**: Los módulos JS deben servirse desde el mismo origen
- **Mitigación**: Flask sirve static files, no hay problema. Verificar que los imports usan rutas relativas correctas.

### Riesgo: Dependencia de `window.*` globals
- **Issue**: Los módulos ES module leen de `window.restaurantId`, etc., que son seteados por `public_base.html`
- **Mitigación**: `menu-state.js` lee al import time (cuando el script se ejecuta, window ya tiene los valores)

### Riesgo: Carrito multi-tab
- **Issue**: `cart.js` ya maneja sincronización entre tabs via `storage` event — funciona sin cambios

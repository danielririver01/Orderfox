# Orderfox Offline PWA Implementation Plan
*Adaptado de Velzia Offline — Riosucio Edition para el proyecto Orderfox (Flask)*

## Explicación Sencilla (Para el equipo)
**Objetivo final**: Que Orderfox funcione aunque se corte el internet (por lluvia, mala señal). El cliente ve el menú, hace su pedido, y cuando vuelva la señal el pedido llega solo al dueño. Nadie nota que hubo corte.

### Paso a paso (adaptado a tu proyecto actual)
Tu proyecto ya usa Flask, plantillas Jinja2, JavaScript vanilla y un Service Worker básico para notificaciones. El plan no te hace cambiar de tecnología, solo suma funciones:

1. **Fase 1: El Búnker (Base offline)**
   - Expandimos tu `sw.js` existente para que guarde en caché el menú, imágenes de Cloudinary y páginas principales.
   - Agregamos una base de datos local en el navegador (IndexedDB, usando Dexie.js) donde se guardan: el menú actual, los pedidos que no se pudieron enviar por falta de internet.
   - Añadimos 3 endpoints nuevos en Flask: `/api/ping` (chequeo de conexión real), `/menu/<slug>/api/hash` (hash del menú actual), `/menu/<slug>/api/delta` (cambios del menú desde última sincronización).

2. **Fase 2: El Ninja (Sincronización automática)**
   - Cuando vuelve la internet, la app la detecta sola (usamos un chequeo real, no el `navigator.onLine` que falla cuando el WiFi está conectado pero no tiene internet).
   - Revisa si el menú cambió, baja solo los cambios (no todo el menú otra vez).
   - Envía automáticamente los pedidos guardados localmente, sin que nadie apriete botones.

3. **Fase 3: La Última Hamburguesa (Conflictos de stock)**
   - Si dos personas piden el mismo producto que solo queda una unidad, el servidor decide quién lo obtiene por orden de llegada (quién llegó primero al servidor, no al celular del cliente).
   - Si un pedido es rechazado (producto agotado), el cliente ve un aviso claro con botón para ver el menú actualizado.

4. **Fase 4: El Escudo (Control para el dueño)**
   - El dueño marca un producto como agotado en su panel. No usamos WebSockets (caros y difíciles de mantener), sino un chequeo cada 30 segundos de los clientes: si el menú cambió, bajan la actualización.
   - Si el menú no se actualiza en 24 horas y no hay internet, se bloquean los pedidos con aviso claro.

5. **Fase 5: Despliegue**
   - Checklist para producción: servidor siempre encendido (no planes gratuitos que se duermen), HTTPS activado (obligatorio para Service Workers), endpoints funcionando correctamente.

---

## Contexto del Proyecto Actual
- **Backend**: Flask + SQLAlchemy + MySQL, multi-tenant (restaurantes con slugs únicos)
- **Frontend**: Jinja2 templates, Vanilla JS, Tailwind CSS v4
- **Service Worker existente**: `app/static/js/sw.js` (solo notificaciones push básicas)
- **Autenticación**: Clerk SDK
- **Imágenes**: Cloudinary
- **Modelos existentes**: Restaurant, Product, Order, OrderItem, Category, etc.

---

## FASE 1: El Búnker (Base Técnica)
### Objetivo
App funciona completamente sin internet: mostrar menú, tomar pedidos y guardarlos localmente.

### Stack ajustado al proyecto
- **Service Worker**: Expandir `app/static/js/sw.js` existente
- **Dexie.js**: Añadir como dependencia frontend (IndexedDB wrapper compatible con Vanilla JS)
- **Workbox**: Integrar vía CDN o npm (coincide con setup existente de Node/Tailwind)
- **Flask Backend**: Añadir nuevos endpoints para sync, ping, hash/delta de menú

### Esquema IndexedDB (ajustado a modelos existentes)
```javascript
// app/static/js/db.js (nuevo archivo)
import Dexie from 'dexie';

export class OrderfoxDB extends Dexie {
  menu!: Dexie.Table<{
    id: string;
    name: string;
    price: number;
    category: string;
    available: boolean;
    imageUrl?: string;
    lastUpdated: number;
  }, string>;
  queue!: Dexie.Table<{
    localId?: number;
    orderId: string;
    items: Array<{ productId: string; quantity: number; modifiers?: Array<{ name: string; extraPrice: number }> }>;
    tableNumber?: string;
    clientTimestamp: number;
    status: 'pending' | 'synced' | 'rejected';
    retries: number;
    restaurantSlug: string;
  }, number>;
  meta!: Dexie.Table<{ key: string; value: string | number }, string>;

  constructor() {
    super('OrderfoxOffline');
    this.version(1).stores({
      menu: 'id, category, available, lastUpdated',
      queue: '++localId, orderId, status, clientTimestamp, restaurantSlug',
      meta: 'key'
    });
  }
}

export const db = new OrderfoxDB();
```

### Estrategia de caché con Workbox (Vanilla JS)
```javascript
// app/static/js/sw.js (expandido)
import { CacheFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { registerRoute } from 'workbox-routing';
import { ExpirationPlugin } from 'workbox-expiration';

// Menú API: sirve desde caché, actualiza en fondo
registerRoute(
  ({ url }) => url.pathname.startsWith('/menu/') && url.pathname.includes('/search'),
  new StaleWhileRevalidate({ cacheName: 'menu-cache' })
);

// Imágenes Cloudinary: caché primero, máximo 50 imágenes por 30 días
registerRoute(
  ({ url }) => url.origin === 'https://res.cloudinary.com',
  new CacheFirst({
    cacheName: 'cloudinary-images',
    plugins: [new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 30 * 24 * 60 * 60 })]
  })
);
```

### Detección de conexión real (no `navigator.onLine`)
```javascript
// app/static/js/connectivity.js (nuevo archivo)
export async function hasRealConnection() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    
    const res = await fetch('/api/ping', {
      method: 'HEAD',
      cache: 'no-store',
      signal: controller.signal
    });
    
    clearTimeout(timeout);
    return res.ok;
  } catch {
    return false;
  }
}

export function watchConnectivity(onChange) {
  const check = async () => onChange(await hasRealConnection());
  
  window.addEventListener('online', check);
  window.addEventListener('offline', check);
  const interval = setInterval(check, 30_000);
  
  return () => {
    window.removeEventListener('online', check);
    window.removeEventListener('offline', check);
    clearInterval(interval);
  };
}
```

### Nuevos endpoints Flask a añadir
1. `GET /api/ping` (public_bp): Devuelve 200 OK para chequeo de conexión
2. `GET /menu/<slug>/api/hash` (menu_bp): Devuelve hash SHA256 del menú actual + timestamp de última actualización
3. `GET /menu/<slug>/api/delta?since=<timestamp>` (menu_bp): Devuelve items del menú actualizados desde `since`

---

## FASE 2: El Ninja (Sincronización Silenciosa)
### Objetivo
Auto-sincronización al volver la conexión, sin acción del usuario.

### Lógica de sincronización (Vanilla JS)
```javascript
// app/static/js/sync.js (nuevo archivo)
import { db } from './db.js';
import { hasRealConnection } from './connectivity.js';

export async function syncMenuIfNeeded(restaurantSlug) {
  const online = await hasRealConnection();
  if (!online) return;

  const savedHash = await db.meta.get('menuHash');
  const res = await fetch(`/menu/${restaurantSlug}/api/hash`);
  const { hash, lastUpdated } = await res.json();

  if (savedHash?.value === hash) return;

  const since = await db.meta.get('lastSync');
  const deltaRes = await fetch(`/menu/${restaurantSlug}/api/delta?since=${since?.value ?? 0}`);
  const { items } = await deltaRes.json();

  await db.transaction('rw', db.menu, db.meta, async () => {
    for (const item of items) await db.menu.put(item);
    await db.meta.put({ key: 'menuHash', value: hash });
    await db.meta.put({ key: 'lastSync', value: lastUpdated });
  });
}

export async function flushQueue(restaurantSlug) {
  const online = await hasRealConnection();
  if (!online) return;

  const pending = await db.queue.where('status').equals('pending').toArray();
  if (pending.length === 0) return;

  for (const order of pending) {
    try {
      const res = await fetch(`/menu/${restaurantSlug}/api/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order)
      });
      const data = await res.json();
      await db.queue.update(order.localId, { status: data.status === 'accepted' ? 'synced' : 'rejected' });
      if (data.status !== 'accepted') notifyRejection(data.reason);
    } catch {
      await db.queue.update(order.localId, { retries: order.retries + 1 });
    }
  }
}
```

### Cuándo disparar la sincronización
Añadir a `app/templates/common/base.html` o plantillas de menú público:
```javascript
// Al cargar la página
syncMenuIfNeeded(currentRestaurantSlug);
flushQueue(currentRestaurantSlug);

// Cada vez que vuelve la conexión
const cleanup = watchConnectivity(async (online) => {
  if (online) {
    await syncMenuIfNeeded(currentRestaurantSlug);
    await flushQueue(currentRestaurantSlug);
  }
});
```

---

## FASE 3: La Última Hamburguesa (Lógica de Conflicto)
### Objetivo
Resolución justa de conflictos de stock: FIFO por llegada al servidor.

### Ajuste a endpoint de pedidos Flask
Actualizar `app/routes/public.py`:
```python
@public_bp.route('/menu/<slug>/api/order', methods=['POST'])
def create_order(slug):
    data = request.get_json()
    server_received_at = datetime.now(timezone.utc)
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()

    for item in data.get('items', []):
        product = Product.query.filter_by(id=item['productId'], restaurant=restaurant).first()
        if not product or not product.is_active:
            return jsonify({
                'status': 'rejected',
                'reason': f'"{product.name if product else "Producto"}" ya no está disponible.'
            }), 409

    order = Order(
        order_id=data['orderId'],
        restaurant=restaurant,
        client_timestamp=data['clientTimestamp'],
        server_received_at=server_received_at,
        status='pending'
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({'status': 'accepted', 'orderId': order.order_id})
```

### Ajuste a modelo Order (`app/models.py`)
Añadir campos:
```python
class Order(db.Model):
    # ... campos existentes ...
    order_id = db.Column(db.String(36), unique=True)
    client_timestamp = db.Column(db.BigInteger)
    server_received_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

---

## FASE 4: El Escudo (Protección para el Dueño)
### Objetivo
El dueño marca productos agotados, los clientes lo ven vía polling (sin WebSockets).

### Utilidad de hash de menú (`app/utils/menu.py` nuevo archivo)
```python
import hashlib, json
from app.models import Product

def get_menu_hash(restaurant):
    products = Product.query.filter_by(restaurant=restaurant, is_active=True).all()
    data = json.dumps([{
        'id': p.id, 'name': p.name, 'price': float(p.price),
        'category': p.category.name, 'available': p.is_active,
        'imageUrl': p.image_url, 'lastUpdated': p.updated_at.timestamp()
    } for p in products], sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()
```

### Banner offline para clientes
Crear `app/templates/components/offline-banner.html`:
```html
<div id="offline-banner" class="fixed bottom-20 inset-x-0 mx-auto max-w-sm z-50 hidden">
  <div class="bg-amber-900/90 backdrop-blur border border-amber-600/50 rounded-2xl px-4 py-3 flex items-center gap-3 shadow-xl">
    <span class="material-symbols-outlined text-amber-400">wifi_off</span>
    <div class="flex flex-col">
      <span class="text-xs font-black text-amber-200 uppercase tracking-wider">Modo offline</span>
      <span class="text-[10px] text-amber-400">Última sync: <span id="last-sync-time">Nunca</span></span>
    </div>
  </div>
</div>
```

### Bloqueo preventivo por menú desactualizado
```javascript
// app/static/js/sync.js
export async function isMenuStale() {
  const lastSync = await db.meta.get('lastSync');
  if (!lastSync) return true;
  const hoursElapsed = (Date.now() - Number(lastSync.value)) / 3_600_000;
  return hoursElapsed > 24;
}
```
Mensaje al cliente: *"Menú sin actualizar hace más de 24 horas. Los pedidos están pausados hasta recuperar conexión."*

---

## FASE 5: El Despliegue (Checklist Producción)
```
✅ Service Worker registrado con scope '/'
✅ HTTPS habilitado (obligatorio para Service Workers)
✅ IndexedDB inicializado antes del primer render
✅ /api/ping respondiendo en <500ms
✅ Endpoints de hash/delta de menú funcionando
✅ Hash del menú se invalida en cada cambio de producto
✅ Servidor siempre caliente (no planes gratuitos con sleep)
✅ Workbox configurado para cachear recursos estáticos
```

---

## Pasos de Implementación (Ordenados)
1. Crear archivos frontend nuevos: `db.js`, `connectivity.js`, `queue.js`, `sync.js`
2. Expandir `app/static/js/sw.js` existente con estrategias Workbox
3. Añadir nuevos endpoints Flask (ping, hash de menú, delta)
4. Actualizar modelo Order con nuevos campos, ejecutar migración
5. Crear `app/utils/menu.py` para utilidades de hash
6. Añadir componente de banner offline
7. Integrar scripts de sincronización en plantillas de menú público
8. Probar flujo completo: offline → tomar pedido → volver conexión → sincronizar

---

## Resumen Ejecutivo
| Fase | Qué resuelve | Tecnología clave |
|------|-------------|-----------------|
| 1 — Búnker | App funciona sin internet | Service Worker + Dexie.js + Workbox |
| 2 — Ninja | Sync silenciosa al volver la señal | Hash delta + polling real |
| 3 — Última Hamburguesa | Conflictos de stock justos | FIFO servidor + rechazo con notificación |
| 4 — Escudo | Dueño controla el menú en tiempo real | Polling 30s (sin WebSockets) |
| 5 — Despliegue | Sin sorpresas en producción | Hosting caliente + HTTPS + checklist |

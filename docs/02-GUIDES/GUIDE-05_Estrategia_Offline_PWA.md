# GUIDE-05: Estrategia Offline y PWA

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Stack Offline

| Tecnología | Propósito | Estado |
|------------|-----------|--------|
| **Workbox** (v7.4.1) | Service worker para caching y PWA | ⚙️ Configurado en `package.json` |
| **Dexie.js** (v4.4.2) | IndexedDB para datos offline | ⚙️ Configurado en `package.json` |
| **localStorage** | Carrito de compras con TTL | ✅ Activo en `cart.js` |
| **Web Storage API** | Sincronización cross-tab | ✅ Activo en `cart.js` |

---

## 2. Carrito Offline (localStorage)

Ubicación: `app/static/js/cart.js`

### Características
- Almacenamiento en `localStorage` con clave `velziaCart_{restaurantId}`
- TTL de 24 horas (el carrito expira automáticamente)
- Sincronización cross-tab via evento `storage`
- Persistencia entre recargas de página

### Estructura
```javascript
const CART_KEY = `velziaCart_${restaurantId}`;
const CART_TTL = 24 * 60 * 60 * 1000; // 24 hours

// Formato en localStorage
{
  items: { "product_id": { quantity: 2, modifiers: [...] } },
  _lastUpdated: 1718558400000  // timestamp Unix
}
```

### Flujo
```
1. Usuario agrega producto al carrito
2. saveCart() guarda en localStorage con timestamp
3. loadCart() verifica TTL antes de cargar
4. Si expiró → limpia carrito automáticamente
5. Cambios en otra pestaña → evento 'storage' → sincroniza
```

---

## 3. Service Worker (Workbox)

### Dependencias
```json
{
  "workbox-core": "^7.4.1",
  "workbox-expiration": "^7.4.1",
  "workbox-precaching": "^7.4.1",
  "workbox-routing": "^7.4.1",
  "workbox-strategies": "^7.4.1",
  "workbox-window": "^7.4.1"
}
```

### Estrategias de Cache Sugeridas

| Recurso | Estrategia | Explicación |
|---------|-----------|-------------|
| `app/static/CSS/output.css` | `StaleWhileRevalidate` | CSS compilado, cambios poco frecuentes |
| `app/static/js/*.js` | `StaleWhileRevalidate` | JS del dashboard, caché + actualización |
| Imágenes de Cloudinary | `CacheFirst` (7 días) | No cambian, servir desde caché |
| `/api/public/menu/*` | `NetworkFirst` | Menú debe estar actualizado |
| Páginas HTML del dashboard | `NetworkOnly` | Siempre fresco (contenido dinámico) |

### Registro del Service Worker
```javascript
// En el template base (app/template/common/base.html)
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js');
}
```

---

## 4. Sincronización Cross-Tab

El carrito usa el evento `storage` del `window` para mantener consistencia entre pestañas:

```javascript
window.addEventListener('storage', (event) => {
    if (event.key === CART_KEY) {
        cart = loadCart();
        updateDisplay();
    }
});
```

Esto asegura que si un usuario:
- Agrega un producto en la pestaña A
- Abre la pestaña B
- El carrito en la pestaña B se actualiza automáticamente

---

## 5. Estrategia de Instalación (PWA)

### Web App Manifest
```json
{
  "name": "Orderfox - Pedidos para Restaurantes",
  "short_name": "Orderfox",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff"
}
```

### Criterios de Instalación
- HTTPS requerido (localhost funciona en desarrollo)
- Service worker registrado y activo
- Manifest.json configurado
- Icono de 192x192 y 512x512

---

## 6. Limitaciones Conocidas

| Aspecto | Situación | Plan |
|---------|-----------|------|
| Service worker | Dependencias instaladas, SW no implementado | Implementar en próxima iteración |
| Dexie (IndexedDB) | Dependencia instalada, no utilizado activamente | Evaluar para caché de menú |
| Sincronización offline | Solo carrito (localStorage) | Extender a pedidos pendientes |
| Push notifications | No implementado | Futura integración |

---

## 7. Próximos Pasos

1. **Implementar service worker** con Workbox para caching de recursos estáticos
2. **Cachear menú público** en IndexedDB via Dexie para visualización offline
3. **Cola de pedidos offline** — permitir crear pedidos sin conexión y enviarlos cuando haya red
4. **Notificaciones push** — alertar al dueño cuando llegue un pedido nuevo

---

## 8. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |

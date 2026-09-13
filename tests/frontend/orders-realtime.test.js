/**
 * orders-realtime.test.js — Regresión de las notificaciones de sistema.
 *
 * Bug: showBrowserNotification() esperaba `navigator.serviceWorker.ready`,
 * promesa que NUNCA se resuelve si no hay un service worker registrado (Velzia
 * no registra ninguno). Resultado: la notificación se quedaba colgada y el
 * fallback `new Notification()` era inalcanzable → no se notificaba nada.
 *
 * Se ejecuta con:  node tests/frontend/orders-realtime.test.js
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const SRC_PATH = process.env.ORDERS_REALTIME_SRC
  || path.join(__dirname, '..', '..', 'app', 'static', 'js', 'orders-realtime.js');

const src = fs.readFileSync(SRC_PATH, 'utf8');

// ─── Stubs de navegador ──────────────────────────────────────────────────────
const shown = [];

class MockNotification {
  constructor(title, options) {
    shown.push({ title, options });
  }
}
MockNotification.permission = 'granted';

class MockBroadcastChannel {
  constructor(name) { this.name = name; }
  postMessage() {}
}

global.window = global;
global.Notification = MockNotification;
global.BroadcastChannel = MockBroadcastChannel;
global.document = {
  addEventListener() {},
  getElementById() { return null; },
};

// Navegador típico de Velzia: SIN service worker registrado. `ready` nunca
// resuelve (comportamiento real de la spec) y `getRegistration()` → undefined.
let readyAccedido = false;
const sinServiceWorker = {
  get ready() {
    readyAccedido = true;
    return new Promise(() => {});
  },
  getRegistration: async () => undefined,
};

Object.defineProperty(global, 'navigator', {
  value: { serviceWorker: sinServiceWorker },
  writable: true,
  configurable: true,
});

eval(src);

function conTimeout(promesa, ms, mensaje) {
  return Promise.race([
    promesa,
    new Promise((_, reject) => setTimeout(() => reject(new Error(mensaje)), ms)),
  ]);
}

(async () => {
  // 1. Sin SW registrado → debe caer al fallback y notificar (antes: se colgaba)
  await conTimeout(
    showBrowserNotification(1),
    1000,
    'showBrowserNotification() se colgó: la notificación nunca se mostró'
  );
  assert.strictEqual(shown.length, 1, 'Debe mostrarse exactamente 1 notificación');
  assert.match(shown[0].title, /Nuevo pedido/, 'Título para un solo pedido');
  assert.ok(!readyAccedido, 'No debe esperarse navigator.serviceWorker.ready');

  // 2. Varios pedidos → título en plural
  await conTimeout(showBrowserNotification(3), 1000, 'Timeout con varios pedidos');
  assert.strictEqual(shown.length, 2, 'Debe mostrarse la segunda notificación');
  assert.match(shown[1].title, /3 pedidos pendientes/, 'Título plural con el conteo');

  // 3. Navegador sin Service Worker API → también debe notificar
  Object.defineProperty(global, 'navigator', {
    value: {},
    writable: true,
    configurable: true,
  });
  await conTimeout(showBrowserNotification(1), 1000, 'Timeout sin Service Worker API');
  assert.strictEqual(shown.length, 3, 'Debe notificar aunque no exista la API');

  // 4. Permiso denegado → no se notifica
  MockNotification.permission = 'denied';
  await conTimeout(showBrowserNotification(1), 1000, 'Timeout con permiso denegado');
  assert.strictEqual(shown.length, 3, 'Con permiso denegado no debe notificar');

  console.log('✔ orders-realtime.js: notificaciones 4/4 OK');
})().catch((err) => {
  console.error('✘ Fallo en test JS:', err.message);
  process.exit(1);
});

// ── Velzia — Full Restaurant Simulation ────────────
// Simula el flujo REAL de un restaurante usando la plataforma:
// 1. Dashboard overview
// 2. Check orders
// 3. Browse products
// 4. Create an order
// 5. Confirm & deliver order
// 6. Open Copilot VZ & ask a question
// 7. Public menu browsing (client side)
import { check, sleep } from 'k6';
import http from 'k6/http';
import { BASE_URL, RESTAURANT_SLUG, loginJWT, authHeaders, checkSuccess, think, tryJSON } from './helpers.js';

export const options = {
  stages: [
    // Fase 1 — ¿Sobrevive?
    { duration: '30s', target: 5 },
    { duration: '1m', target: 10 },
    // Fase 2 — Uso real
    { duration: '1m', target: 20 },
    { duration: '2m', target: 30 },
    // Fase 3 — Estrés
    { duration: '1m', target: 50 },
    { duration: '2m', target: 80 },
    { duration: '1m', target: 120 },
    // Cooldown
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(90)<3000', 'p(95)<5000'],
    http_req_failed: ['rate<0.05'],
    http_reqs: ['rate>5'],
  },
};

// ── Private business user flow ─────────
function businessFlow(token) {
  const headers = authHeaders(token);

  // Dashboard overview
  let r = http.get(`${BASE_URL}/api/dashboard/overview`, { headers });
  check(r, { 'overview loaded': (x) => x.status === 200 });
  think(0.5);

  // Extended stats
  r = http.get(`${BASE_URL}/api/dashboard/stats?range=today`, { headers });
  check(r, { 'stats today': (x) => x.status === 200 });
  think(0.3);

  // Weekly stats
  r = http.get(`${BASE_URL}/api/dashboard/stats?range=week`, { headers });
  check(r, { 'stats week': (x) => x.status === 200 });
  think(0.3);

  // Order polling
  r = http.get(`${BASE_URL}/api/dashboard/check-orders`, { headers });
  check(r, { 'order polling': (x) => x.status === 200 });
  think(0.3);

  // List orders
  r = http.get(`${BASE_URL}/api/orders?sort=desc&per_page=10`, { headers });
  const ordersOk = check(r, { 'orders list': (x) => x.status === 200 });
  let firstOrderId = null;
  if (ordersOk) {
    const orders = tryJSON(r.body)?.data?.orders;
    if (orders && orders.length > 0) firstOrderId = orders[0].id;
  }
  think(0.5);

  // View order detail
  if (firstOrderId) {
    r = http.get(`${BASE_URL}/api/orders/${firstOrderId}`, { headers });
    check(r, { 'order detail': (x) => x.status === 200 });
    think(0.3);
  }

  // List products
  r = http.get(`${BASE_URL}/api/products?active_only=true`, { headers });
  check(r, { 'products list': (x) => x.status === 200 });
  const products = tryJSON(r.body)?.data?.products || [];
  think(0.5);

  // List categories
  r = http.get(`${BASE_URL}/api/categories`, { headers });
  check(r, { 'categories list': (x) => x.status === 200 });
  think(0.3);

  // Create a simple order
  const productName = products.length > 0
    ? products[0].name
    : 'Producto de prueba';
  const productPrice = products.length > 0
    ? products[0].price
    : 15000;

  const newOrder = {
    customer_name: 'Cliente k6',
    items: [
      { product_name: productName, product_price: productPrice, quantity: 1, modifiers: [] },
    ],
  };
  r = http.post(`${BASE_URL}/api/orders`, JSON.stringify(newOrder), { headers });
  const created = check(r, { 'order created': (x) => x.status === 201 });
  think(0.5);

  // Confirm the order
  if (created) {
    const orderId = tryJSON(r.body)?.data?.id;
    if (orderId) {
      r = http.patch(
        `${BASE_URL}/api/orders/${orderId}/status`,
        JSON.stringify({ status: 'confirmed' }),
        { headers }
      );
      check(r, { 'order confirmed': (x) => x.status === 200 });
      think(0.3);

      // Delete the test order
      r = http.del(`${BASE_URL}/api/orders/${orderId}`, null, { headers });
      check(r, { 'order cleaned': (x) => x.status === 200 });
    }
  }
  think(0.5);

  // Copilot — quick question
  r = http.get(`${BASE_URL}/insights/api/conversations`, { headers });
  if (r.status === 200) {
    const convs = tryJSON(r.body)?.data || [];
    let convId = convs.length > 0 ? convs[0].id : null;

    if (!convId) {
      r = http.post(
        `${BASE_URL}/insights/api/conversations`,
        JSON.stringify({ title: 'Test rápido' }),
        { headers }
      );
      convId = tryJSON(r.body)?.data?.id;
      think(0.5);
    }

    if (convId) {
      r = http.post(
        `${BASE_URL}/insights/api/conversations/${convId}/messages`,
        JSON.stringify({ content: '¿Cuántos pedidos tengo hoy?', type: 'quick' }),
        { headers }
      );
      check(r, { 'copilot answer': (x) => x.status === 200 });
      think(2);
    }
  }
}

// ── Public menu client flow ────────────
function publicFlow() {
  let r = http.get(`${BASE_URL}/api/public/menu/${RESTAURANT_SLUG}`);
  const menuOk = check(r, { 'public menu': (x) => x.status === 200 });
  if (menuOk) {
    const cats = tryJSON(r.body)?.data?.categories || [];
    for (let i = 0; i < Math.min(cats.length, 3); i++) {
      if (cats[i].id) {
        r = http.get(
          `${BASE_URL}/api/public/menu/${RESTAURANT_SLUG}/categoria/${cats[i].id}`
        );
        check(r, { [`category ${i} loaded`]: (x) => x.status === 200 });
        think(0.3);
      }
    }
  }
}

export default function () {
  // 70% probability: business user flow
  if (Math.random() < 0.7) {
    const token = loginJWT();
    if (token) {
      businessFlow(token);
    }
  }

  // 30% probability: public menu browsing (no auth)
  if (Math.random() < 0.3) {
    publicFlow();
  }
}

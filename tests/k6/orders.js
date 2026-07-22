// ── Velzia — Orders test ───────────────────────────
// Simula: listar pedidos, ver detalle, crear pedido, cambiar estado
import { check, sleep } from 'k6';
import http from 'k6/http';
import { BASE_URL, loginJWT, authHeaders, checkSuccess, think, tryJSON } from './helpers.js';

export const options = {
  stages: [
    { duration: '30s', target: 5 },
    { duration: '1m', target: 15 },
    { duration: '30s', target: 30 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const token = loginJWT();
  if (!token) return;
  const headers = authHeaders(token);

  // 1. List today's orders
  const listOrders = http.get(`${BASE_URL}/api/orders?sort=desc`, { headers });
  const listOk = checkSuccess(listOrders, 'list orders');
  think(1);

  // 2. If we have orders, view one
  let firstOrderId = null;
  if (listOk) {
    const body = tryJSON(listOrders.body);
    const orders = body?.data?.orders;
    if (orders && orders.length > 0) {
      firstOrderId = orders[0].id;
      const detail = http.get(`${BASE_URL}/api/orders/${firstOrderId}`, { headers });
      checkSuccess(detail, 'order detail');
      think(0.7);

      // 3. Get receipt
      const receipt = http.get(`${BASE_URL}/api/orders/${firstOrderId}/receipt`, { headers });
      checkSuccess(receipt, 'order receipt');
      think(0.5);
    }
  }

  // 4. Create a new order
  const newOrder = {
    customer_name: 'K6 Test',
    customer_phone: '3001234567',
    items: [
      {
        product_id: null,
        product_name: 'Producto de prueba',
        product_price: 15000,
        quantity: 2,
        modifiers: [],
      },
    ],
  };
  const created = http.post(`${BASE_URL}/api/orders`, JSON.stringify(newOrder), { headers });
  const createOk = checkSuccess(created, 'create order');
  think(1);

  // 5. Change status of created order
  if (createOk) {
    const body = tryJSON(created.body);
    const orderId = body?.data?.id;
    if (orderId) {
      const statusUpdate = http.patch(
        `${BASE_URL}/api/orders/${orderId}/status`,
        JSON.stringify({ status: 'confirmed' }),
        { headers }
      );
      checkSuccess(statusUpdate, 'confirm order');
      think(0.5);

      // Cancel it
      const cancel = http.post(`${BASE_URL}/api/orders/${orderId}/cancel`, null, { headers });
      checkSuccess(cancel, 'cancel order');
      think(0.5);

      // Delete it
      const del = http.del(`${BASE_URL}/api/orders/${orderId}`, null, { headers });
      checkSuccess(del, 'delete order');
      think(0.3);
    }
  }

  // 6. Load orders page (HTML)
  const ordersPage = http.get(`${BASE_URL}/orders`, { headers });
  checkSuccess(ordersPage, 'orders page');
  think(1);
}

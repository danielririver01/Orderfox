// ── Velzia — Products & Categories test ────────────
// Simula: listar categorías, productos, crear/editar
import { check, sleep } from 'k6';
import http from 'k6/http';
import { BASE_URL, loginJWT, authHeaders, checkSuccess, think, tryJSON } from './helpers.js';

export const options = {
  stages: [
    { duration: '30s', target: 5 },
    { duration: '1m', target: 10 },
    { duration: '30s', target: 20 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2500'],
    http_req_failed: ['rate<0.03'],
  },
};

export default function () {
  const token = loginJWT();
  if (!token) return;
  const headers = authHeaders(token);

  // 1. List products
  const products = http.get(`${BASE_URL}/api/products`, { headers });
  const prodOk = checkSuccess(products, 'list products');
  think(0.5);

  // 2. List categories
  const cats = http.get(`${BASE_URL}/api/categories`, { headers });
  const catOk = checkSuccess(cats, 'list categories');
  think(0.5);

  // 3. View a product if any exist
  if (prodOk) {
    const body = tryJSON(products.body);
    const list = body?.data?.products;
    if (list && list.length > 0) {
      const detail = http.get(`${BASE_URL}/api/products/${list[0].id}`, { headers });
      checkSuccess(detail, 'product detail');
      think(0.5);
    }
  }

  // 4. Load products HTML page
  const prodPage = http.get(`${BASE_URL}/products/`, { headers });
  checkSuccess(prodPage, 'products page');
  think(1);

  // 5. Load categories HTML page
  const catPage = http.get(`${BASE_URL}/categories/`, { headers });
  checkSuccess(catPage, 'categories page');
  think(0.5);
}

// ── Velzia — Public Menu test ──────────────────────
// Simula: un cliente viendo el menú digital público
import { check, sleep } from 'k6';
import http from 'k6/http';
import { BASE_URL, RESTAURANT_SLUG, checkSuccess, think, tryJSON } from './helpers.js';

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 30 },
    { duration: '30s', target: 50 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.02'],
  },
};

export default function () {
  // 1. Public menu API — get all categories & products
  const menu = http.get(`${BASE_URL}/api/public/menu/${RESTAURANT_SLUG}`);
  const menuOk = check(menu, {
    'menu loaded': (r) => r.status === 200,
    'menu has data': (r) => {
      const d = tryJSON(r.body);
      return d && d.success && !!d.data;
    },
  });
  think(1.5);

  if (!menuOk) {
    // Maybe the restaurant slug is wrong; try the basic endpoint
    console.warn(`[public-menu] Menu not found for slug "${RESTAURANT_SLUG}"`);
    return;
  }

  // 2. Browse categories
  const body = tryJSON(menu.body);
  const categories = body?.data?.categories || [];
  if (categories.length > 0) {
    const firstCat = categories[0];
    if (firstCat.id) {
      const catProducts = http.get(
        `${BASE_URL}/api/public/menu/${RESTAURANT_SLUG}/categoria/${firstCat.id}`
      );
      checkSuccess(catProducts, 'category products');
      think(1);
    }
  }

  // 3. Browse all categories (simulate browsing through menu)
  for (let i = 0; i < Math.min(categories.length, 5); i++) {
    if (categories[i].id) {
      const catView = http.get(
        `${BASE_URL}/api/public/menu/${RESTAURANT_SLUG}/categoria/${categories[i].id}`
      );
      check(catView, { [`category ${categories[i].name} loaded`]: (r) => r.status === 200 });
      think(0.5);
    }
  }

  // 4. Get novedades (new products)
  const novedades = http.get(
    `${BASE_URL}/api/public/menu/${RESTAURANT_SLUG}/novedades?page=1&per_page=12`
  );
  checkSuccess(novedades, 'novedades');
  think(0.5);
}

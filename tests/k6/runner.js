// ── Velzia Stress Test Runner ───────────────────────
// Ejecuta todos los tests secuencialmente y consolida resultados
// Uso: k6 run tests/k6/runner.js
import { group, check, sleep } from 'k6';
import http from 'k6/http';
import { VELZIA_URL, VELZIA_EMAIL, VELZIA_PASSWORD, VELZIA_SLUG } from './config.js';

export const options = {
  vus: 1,
  duration: '1s',
  iterations: 1,
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    http_req_failed: ['rate<0.1'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'count'],
};

function checkResponse(r, expectedStatus = 200) {
  return r.status === expectedStatus;
}

function getJSON(r) {
  try { return JSON.parse(r.body); } catch { return null; }
}

function report(name, status, detail = '') {
  const icon = status ? '✅' : '❌';
  console.log(`${icon} ${name}${detail ? ': ' + detail : ''}`);
}

const BASE_URL = VELZIA_URL;

export default function () {
  console.log('═══════════════════════════════════════');
  console.log('  VELZIA — Stress Test Suite Runner');
  console.log(`  Target: ${BASE_URL}`);
  console.log('═══════════════════════════════════════\n');

  // ── Phase 0: Health Check ──────────────────
  group('🌡️  Health Check', () => {
    const r = http.get(`${BASE_URL}/`);
    report('Web root', checkResponse(r), `${r.status}`);
    const r2 = http.get(`${BASE_URL}/api/auth/plans`);
    report('API plans', checkResponse(r2), `${r2.status}`);
    const d = getJSON(r2);
    report('API response structure', d && d.success, d ? `success=${d.success}` : 'failed to parse');
  });

  // ── Phase 1: Public Menu ───────────────────
  group('📋 Public Menu', () => {
    const r = http.get(`${BASE_URL}/api/public/menu/${VELZIA_SLUG}`);
    report('Menu loaded', checkResponse(r), `${r.status}`);
    const d = getJSON(r);
    if (d?.data?.categories) {
      report('Categories count', true, `${d.data.categories.length} categories`);
      if (d.data.categories.length > 0) {
        for (const cat of d.data.categories.slice(0, 3)) {
          const cr = http.get(`${BASE_URL}/api/public/menu/${VELZIA_SLUG}/categoria/${cat.id}`);
          report(`Category "${cat.name}"`, checkResponse(cr), `${cr.status}`);
        }
      }
    } else {
      report('Categories', false, 'no categories data');
    }
    const nr = http.get(`${BASE_URL}/api/public/menu/${VELZIA_SLUG}/novedades?page=1&per_page=6`);
    report('Novedades', checkResponse(nr), `${nr.status}`);
  });

  // ── Phase 2: API Login ─────────────────────
  group('🔐 Authentication', () => {
    if (!VELZIA_EMAIL || !VELZIA_PASSWORD) {
      report('Credentials', false, 'VELZIA_EMAIL / VELZIA_PASSWORD not set — skipping auth tests');
      return;
    }
    const r = http.post(`${BASE_URL}/api/auth/login`,
      JSON.stringify({ email: VELZIA_EMAIL, password: VELZIA_PASSWORD }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    report('API login', checkResponse(r), `${r.status}`);
    const d = getJSON(r);
    if (d?.success && d?.data?.access_token) {
      report('Token obtained', true, `${d.data.access_token.substring(0, 20)}...`);
      const headers = {
        'Authorization': `Bearer ${d.data.access_token}`,
        'Content-Type': 'application/json',
      };

      // Dashboard
      const ov = http.get(`${BASE_URL}/api/dashboard/overview`, { headers });
      report('Dashboard overview', checkResponse(ov), `${ov.status}`);

      const st = http.get(`${BASE_URL}/api/dashboard/stats?range=today`, { headers });
      report('Dashboard stats', checkResponse(st), `${st.status}`);

      // Products
      const pr = http.get(`${BASE_URL}/api/products?per_page=5`, { headers });
      report('Products list', checkResponse(pr), `${pr.status}`);
      const pd = getJSON(pr);
      if (pd?.data?.products) {
        report('Products count', true, `${pd.data.products.length} products`);
        if (pd.data.products.length > 0) {
          const pdr = http.get(`${BASE_URL}/api/products/${pd.data.products[0].id}`, { headers });
          report('Product detail', checkResponse(pdr), `${pdr.status}`);
        }
      }

      // Categories
      const ca = http.get(`${BASE_URL}/api/categories`, { headers });
      report('Categories API', checkResponse(ca), `${ca.status}`);

      // Orders
      const or = http.get(`${BASE_URL}/api/orders?per_page=5`, { headers });
      report('Orders list', checkResponse(or), `${or.status}`);

      // Settings
      const se = http.get(`${BASE_URL}/api/dashboard/settings`, { headers });
      report('Settings API', checkResponse(se), `${se.status}`);

      // Copilot (solo list conversations)
      const co = http.get(`${BASE_URL}/insights/api/conversations`, { headers });
      report('Copilot conversations', checkResponse(co), `${co.status}`);
    } else {
      const msg = d?.message || d?.error || 'unknown error';
      report('Auth', false, msg);
    }
  });

  // ── Phase 3: Summary ───────────────────────
  console.log('\n═══════════════════════════════════════');
  console.log('  Runner complete!');
  console.log('  Run individual tests with:');
  console.log(`    k6 run tests/k6/login.js`);
  console.log(`    k6 run tests/k6/dashboard.js`);
  console.log(`    k6 run tests/k6/orders.js`);
  console.log(`    k6 run tests/k6/products.js`);
  console.log(`    k6 run tests/k6/copilot.js`);
  console.log(`    k6 run tests/k6/menu_public.js`);
  console.log(`    k6 run tests/k6/full_restaurant.js`);
  console.log('═══════════════════════════════════════\n');
}

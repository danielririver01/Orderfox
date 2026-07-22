// ── Velzia — Dashboard test ─────────────────────────
// Simula: navegación del dashboard (overview, stats, settings)
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
  // Login once per VU
  const token = loginJWT();
  if (!token) {
    console.warn('[dashboard] login failed, skipping VU');
    return;
  }
  const headers = authHeaders(token);

  // 1. GET /dashboard/ (HTML page)
  const homePage = http.get(`${BASE_URL}/dashboard/`, { headers });
  checkSuccess(homePage, 'dashboard page');
  think(1.5);

  // 2. GET /api/dashboard/overview (stats today)
  const overview = http.get(`${BASE_URL}/api/dashboard/overview`, { headers });
  checkSuccess(overview, 'overview');
  think(0.5);

  // 3. GET /api/dashboard/stats (extended stats)
  const stats = http.get(`${BASE_URL}/api/dashboard/stats?range=today`, { headers });
  checkSuccess(stats, 'stats');
  think(0.5);

  // 4. GET /api/dashboard/stats (weekly)
  const statsWeek = http.get(`${BASE_URL}/api/dashboard/stats?range=week`, { headers });
  checkSuccess(statsWeek, 'stats week');
  think(0.5);

  // 5. GET /api/dashboard/settings
  const settings = http.get(`${BASE_URL}/api/dashboard/settings`, { headers });
  checkSuccess(settings, 'settings');
  think(1);

  // 6. GET /dashboard/settings (HTML)
  const settingsPage = http.get(`${BASE_URL}/dashboard/settings`, { headers });
  checkSuccess(settingsPage, 'settings page');
  think(0.5);

  // 7. GET /api/dashboard/check-orders (polling)
  const poll = http.get(`${BASE_URL}/api/dashboard/check-orders`, { headers });
  checkSuccess(poll, 'order polling');
  think(0.3);
}

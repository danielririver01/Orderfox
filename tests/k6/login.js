// ── Velzia — Login flow test ────────────────────────
// Simula: inicio de sesión vía API y web
import { check, sleep } from 'k6';
import http from 'k6/http';
import { BASE_URL, TEST_EMAIL, TEST_PASSWORD, authHeaders, tryJSON } from './helpers.js';

export const options = {
  stages: [
    { duration: '30s', target: 5 },
    { duration: '30s', target: 10 },
    { duration: '30s', target: 20 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  // 1. Web login page (GET)
  const loginPage = http.get(`${BASE_URL}/`);
  check(loginPage, {
    'login page loaded': (r) => r.status === 200,
    'login page has form': (r) => r.body && r.body.includes('form'),
  });
  sleep(1);

  // 2. API login (POST) — JWT
  const payload = JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD });
  const apiLogin = http.post(`${BASE_URL}/api/auth/login`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const apiOk = check(apiLogin, {
    'api login success': (r) => r.status === 200,
    'api login returns token': (r) => {
      const d = tryJSON(r.body);
      return d && d.success && !!d.data?.access_token;
    },
  });

  if (!apiOk) {
    console.warn(`[login] API login failed for user ${TEST_EMAIL}`);
    return;
  }

  const token = tryJSON(apiLogin.body).data.access_token;
  const headers = authHeaders(token);

  // 3. Verify token — hit a protected endpoint
  const verify = http.get(`${BASE_URL}/api/dashboard/overview`, { headers });
  check(verify, {
    'token verified — overview accessible': (r) => r.status === 200,
  });

  // 4. Load plans endpoint (public)
  const plans = http.get(`${BASE_URL}/api/auth/plans`);
  check(plans, {
    'plans endpoint works': (r) => r.status === 200,
  });

  sleep(0.5);
}

// ── Velzia Stress Test — Shared helpers ──────────────
import { check, sleep } from 'k6';
import http from 'k6/http';

export const BASE_URL = __ENV.VELZIA_URL || 'http://localhost:5000';
export const TEST_EMAIL = __ENV.VELZIA_EMAIL || 'stress@velzia.co';
export const TEST_PASSWORD = __ENV.VELZIA_PASSWORD || 'stress1234';
export const RESTAURANT_SLUG = __ENV.VELZIA_SLUG || 'velzia-stress';

// Login via API (JWT) — returns access token
export function loginJWT() {
  const payload = JSON.stringify({
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
  });
  const res = http.post(`${BASE_URL}/api/auth/login`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, {
    'api login status 200': (r) => r.status === 200,
    'api login has token': (r) => {
      try { return JSON.parse(r.body).data?.access_token?.length > 0; }
      catch { return false; }
    },
  });
  let token = null;
  try { token = JSON.parse(res.body).data?.access_token; } catch {}
  return token;
}

// Auth headers for API calls
export function authHeaders(token) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
}

// Helper: parse JSON safely
export function tryJSON(body) {
  try { return JSON.parse(body); } catch { return null; }
}

// Pause between actions (simulate user think time)
export function think(secs) {
  sleep(secs || 1);
}

// Standard HTTP response checks
export function checkSuccess(res, label = 'request') {
  return check(res, {
    [`${label} status 2xx`]: (r) => r.status >= 200 && r.status < 300,
    [`${label} body has success`]: (r) => {
      const d = tryJSON(r.body);
      return d && d.success === true;
    },
  });
}

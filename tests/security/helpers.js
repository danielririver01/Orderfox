import http from 'k6/http';
import { BASE_URL, VELZIA_EMAIL, VELZIA_PASSWORD } from './config.js';

export function loginJWT() {
  const res = http.post(`${BASE_URL}/api/auth/login`,
    JSON.stringify({ email: VELZIA_EMAIL, password: VELZIA_PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  if (res.status !== 200) return null;
  try { return JSON.parse(res.body).data?.access_token; } catch { return null; }
}

export function authHeaders(token) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
}

export function tryJSON(body) {
  try { return JSON.parse(body); } catch { return null; }
}

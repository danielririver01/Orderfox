// ── Velzia — Copilot VZ test ───────────────────────
// Simula: abrir Copilot VZ, enviar consultas rápidas
import { check, sleep } from 'k6';
import http from 'k6/http';
import { BASE_URL, loginJWT, authHeaders, checkSuccess, think, tryJSON } from './helpers.js';

export const options = {
  stages: [
    { duration: '30s', target: 3 },
    { duration: '1m', target: 8 },
    { duration: '30s', target: 15 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const token = loginJWT();
  if (!token) return;
  const headers = authHeaders(token);

  // 1. Load Copilot page (HTML)
  const page = http.get(`${BASE_URL}/insights/`, { headers });
  checkSuccess(page, 'copilot page');
  think(2);

  // 2. List conversations
  const conversations = http.get(`${BASE_URL}/insights/api/conversations`, { headers });
  const convOk = checkSuccess(conversations, 'list conversations');
  think(0.5);

  let convId = null;
  if (convOk) {
    const body = tryJSON(conversations.body);
    const list = body?.data;
    if (list && list.length > 0) {
      convId = list[0].id;
    }
  }

  // 3. If no conversation exists, create one
  if (!convId) {
    const created = http.post(
      `${BASE_URL}/insights/api/conversations`,
      JSON.stringify({ title: 'Test k6' }),
      { headers }
    );
    if (checkSuccess(created, 'create conversation')) {
      convId = tryJSON(created.body)?.data?.id;
    }
    think(0.5);
  }

  if (!convId) {
    console.warn('[copilot] could not create conversation');
    return;
  }

  // 4. Send a quick message (no LLM, just SQL)
  const msg = http.post(
    `${BASE_URL}/insights/api/conversations/${convId}/messages`,
    JSON.stringify({ content: '¿Cuántas ventas tuve hoy?', type: 'quick' }),
    { headers }
  );
  checkSuccess(msg, 'quick message');
  think(3);

  // 5. Retrieve conversation messages
  const msgs = http.get(
    `${BASE_URL}/insights/api/conversations/${convId}/messages`,
    { headers }
  );
  checkSuccess(msgs, 'get messages');
  think(0.5);
}

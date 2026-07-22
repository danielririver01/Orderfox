import { check } from 'k6';
import http from 'k6/http';
import encoding from 'k6/encoding';
import { BASE_URL } from './config.js';
import { loginJWT, authHeaders, tryJSON } from './helpers.js';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    checks: ['rate==1.0'],
  },
};

function base64Decode(str) {
  const s = str.replace(/-/g, '+').replace(/_/g, '/');
  const padded = s + '='.repeat((4 - s.length % 4) % 4);
  try {
    const raw = encoding.b64decode(padded);
    return JSON.parse(String.fromCharCode(...new Uint8Array(raw)));
  } catch { return null; }
}

export default function () {
  let score = 100;
  let issues = [];

  console.log('═══════════════════════════════════');
  console.log('  JWT Security Audit');
  console.log('═══════════════════════════════════');

  // 1. Login y obtener token
  const token = loginJWT();
  if (!token) {
    console.log('  ❌ JWT: No se pudo obtener token');
    console.log('  JWT Score: 0/100\n');
    return;
  }
  console.log('  ✅ Token obtenido correctamente');

  // 2. Decodificar payload
  const parts = token.split('.');
  if (parts.length !== 3) {
    console.log('  ❌ JWT: Formato inválido (no tiene 3 partes)');
    console.log('  JWT Score: 0/100\n');
    return;
  }

  const payload = base64Decode(parts[1]);
  if (!payload) {
    console.log('  ❌ JWT: No se pudo decodificar el payload');
    score -= 30;
    return;
  }

  // 3. Verificar claims de seguridad
  const now = Math.floor(Date.now() / 1000);

  // exp
  if (!payload.exp) {
    console.log('  ❌ exp: No tiene fecha de expiración');
    score -= 20;
    issues.push('exp');
  } else if (payload.exp > now + 86400) {
    console.log('  ⚠️  exp: Token expira en más de 24h (>86400s)');
    score -= 10;
    issues.push('exp-too-long');
  } else {
    console.log(`  ✅ exp: Token expira correctamente (${Math.round(payload.exp - now)}s)`);
  }

  // iat
  if (!payload.iat) {
    console.log('  ❌ iat: No tiene fecha de emisión');
    score -= 10;
    issues.push('iat');
  } else {
    console.log('  ✅ iat: Fecha de emisión presente');
  }

  // nbf
  if (payload.nbf && payload.nbf > now) {
    console.log('  ⚠️  nbf: Token no es válido aún (fecha futura)');
    score -= 5;
    issues.push('nbf');
  } else {
    console.log('  ✅ nbf: Sin problemas');
  }

  // sub
  if (!payload.sub) {
    console.log('  ❌ sub: No tiene subject (identificador de usuario)');
    score -= 15;
    issues.push('sub');
  } else {
    console.log(`  ✅ sub: Subject presente (${payload.sub})`);
  }

  // jti
  if (!payload.jti) {
    console.log('  ⚠️  jti: No tiene ID único (dificulta revocación)');
    score -= 5;
    issues.push('jti');
  } else {
    console.log('  ✅ jti: ID único presente');
  }

  // iss
  if (!payload.iss) {
    console.log('  ⚠️  iss: No tiene issuer');
    score -= 3;
    issues.push('iss');
  } else {
    console.log('  ✅ iss: Issuer presente');
  }

  // 4. Probar token modificado
  const headers = authHeaders(token);
  const modPayload = { ...payload, sub: '999', role: 'admin' };
  const modB64 = encoding.b64encode(JSON.stringify(modPayload)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const fakeToken = [parts[0], modB64, parts[2]].join('.');
  const r = http.get(`${BASE_URL}/api/dashboard/overview`, {
    headers: { 'Authorization': `Bearer ${fakeToken}`, 'Content-Type': 'application/json' },
  });
  if (r.status === 200) {
    console.log('  ❌ Tampering: Token modificado fue aceptado!');
    score -= 25;
    issues.push('tampering');
  } else {
    console.log('  ✅ Tampering: Token modificado rechazado');
  }

  // 5. Probar token expirado
  const expPayload = { ...payload, exp: now - 3600 };
  const expB64 = encoding.b64encode(JSON.stringify(expPayload)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const expToken = [parts[0], expB64, parts[2]].join('.');
  const r2 = http.get(`${BASE_URL}/api/dashboard/overview`, {
    headers: { 'Authorization': `Bearer ${expToken}`, 'Content-Type': 'application/json' },
  });
  if (r2.status === 200) {
    console.log('  ❌ Expired: Token expirado fue aceptado!');
    score -= 20;
    issues.push('expired');
  } else {
    console.log('  ✅ Expired: Token expirado rechazado');
  }

  // 6. Probar sin token
  const r3 = http.get(`${BASE_URL}/api/dashboard/overview`);
  if (r3.status === 401) {
    console.log('  ✅ NoAuth: Sin token devuelve 401');
  } else {
    console.log('  ❌ NoAuth: Sin token NO devuelve 401');
    score -= 10;
    issues.push('noauth');
  }

  const finalScore = Math.max(0, score);
  console.log(`\n  JWT Score: ${finalScore}/100`);
  if (issues.length > 0) {
    console.log(`  Issues: ${issues.join(', ')}`);
  }
  console.log('═══════════════════════════════════\n');
}

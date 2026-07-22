import { check } from 'k6';
import http from 'k6/http';
import { BASE_URL } from './config.js';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    checks: ['rate==1.0'],
  },
};

// k6 stores header names in original case, so look up case-insensitively
function getHeader(headers, name) {
  const lower = name.toLowerCase();
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === lower) return headers[key];
  }
  return undefined;
}

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': ['DENY', 'SAMEORIGIN'],
  'X-XSS-Protection': '0',
  'Strict-Transport-Security': null,
  'Content-Security-Policy': null,
  'Referrer-Policy': null,
  'Permissions-Policy': null,
};

export default function () {
  const urls = [
    `${BASE_URL}/`,
    `${BASE_URL}/api/auth/plans`,
    `${BASE_URL}/api/public/menu/demo`,
  ];

  const results = {};
  let score = 100;
  let totalChecks = 0;
  let passedChecks = 0;

  for (const url of urls) {
    const r = http.get(url);
    const headers = r.headers;

    for (const [header, expected] of Object.entries(SECURITY_HEADERS)) {
      const actual = getHeader(headers, header);
      totalChecks++;

      let pass = false;
      if (!expected) {
        pass = actual !== undefined;
      } else if (Array.isArray(expected)) {
        pass = expected.includes(actual);
      } else {
        pass = actual === expected;
      }

      if (pass) passedChecks++;

      const headerKey = header.replace(/-/g, '');
      if (!results[headerKey]) results[headerKey] = { present: 0, total: 0 };
      results[headerKey].total++;
      if (pass) results[headerKey].present++;
    }
  }

  console.log('═══════════════════════════════════');
  console.log('  Security Headers Audit');
  console.log('═══════════════════════════════════');
  for (const [header, data] of Object.entries(results)) {
    const pct = Math.round((data.present / data.total) * 100);
    const icon = pct === 100 ? 'PASS' : pct >= 50 ? 'WARN' : 'FAIL';
    console.log(`  ${icon} ${header}: ${pct}% (${data.present}/${data.total})`);
    if (pct < 100) score -= (100 - pct) / data.total;
  }

  const finalScore = Math.max(0, Math.round(score));
  console.log(`\n  Headers Score: ${finalScore}/100`);
  console.log('═══════════════════════════════════\n');
}

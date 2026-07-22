// ── Velzia Stress Test — default config ────────────
// Sobrescribe con variables de entorno:
//   VELZIA_URL=http://localhost:5000
//   VELZIA_EMAIL=admin@demo.com
//   VELZIA_PASSWORD=123456
//   VELZIA_SLUG=demo
export const VELZIA_URL = __ENV.VELZIA_URL || 'http://localhost:5000';
export const VELZIA_EMAIL = __ENV.VELZIA_EMAIL || 'stress@velzia.co';
export const VELZIA_PASSWORD = __ENV.VELZIA_PASSWORD || 'stress1234';
export const VELZIA_SLUG = __ENV.VELZIA_SLUG || 'velzia-stress';

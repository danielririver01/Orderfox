/**
 * urls.ts — Orígenes de los servicios para la landing.
 *
 * Astro (esta app) y Flask (auth, planes, legal) viven en orígenes distintos:
 *  - Dev:  Astro :4321, Flask :5000 (por eso `/login` aquí caería en el
 *          catch-all [slug] y mostraría "Error al cargar el menú").
 *  - Prod: landing en velzia.shop (Vercel), Flask en su propio dominio/VPS.
 *
 * Los CTAs de la landing SIEMPRE deben usar estas constantes, nunca rutas
 * relativas de Astro.
 *
 * Env:
 *  - PUBLIC_FLASK_URL: origen de Flask (default: http://localhost:5000)
 *      dev:  http://localhost:5000
 *      prod: https://api.velzia.shop (o el dominio donde corre Gunicorn)
 */

function withTrailingSlash(url: string): string {
  return url.endsWith('/') ? url : `${url}/`;
}

export const FLASK_URL = withTrailingSlash(
  import.meta.env.PUBLIC_FLASK_URL || 'http://localhost:5000',
);

/** Login de Flask (auth.login vive en /login desde v1.5). */
export const LOGIN_URL = `${FLASK_URL}login`;

/** Pricing de Flask (mismo flujo de compra que /planes). */
export const PLANS_URL = `${FLASK_URL}planes`;

/** Legal (términos, privacidad, datos). */
export const LEGAL_URL = `${FLASK_URL}legal`;

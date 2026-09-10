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
 *      prod: https://velzia.shop
 */

function withTrailingSlash(url: string): string {
  return url.endsWith('/') ? url : `${url}/`;
}

function resolveFlaskUrl(): string {
  const envUrl = import.meta.env.PUBLIC_FLASK_URL;
  if (envUrl) return envUrl;

  if (import.meta.env.MODE === 'production') return 'https://velzia.shop';

  return 'http://localhost:5000';
}

export const FLASK_URL = withTrailingSlash(resolveFlaskUrl());

/** Login de Flask (auth.login vive en /login desde v1.5). */
export const LOGIN_URL = `${FLASK_URL}login`;

/** Registro con plan preseleccionado (Flask /register?plan=...). */
export function registerUrl(plan: string): string {
  return `${FLASK_URL}register?plan=${encodeURIComponent(plan)}`;
}

/** Pricing de Flask (mismo flujo de compra que /planes). */
export const PLANS_URL = `${FLASK_URL}planes`;

/** Legal (términos, privacidad, datos). */
export const LEGAL_URL = `${FLASK_URL}legal`;

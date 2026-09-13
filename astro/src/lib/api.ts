import type { MenuResponse, Category, Product } from './types';

/**
 * API pública del menú (Flask).
 * - Prod (default): https://velzia.shop/api/public — igual que siempre.
 * - Dev local: define PUBLIC_MENU_API_URL=http://localhost:5000/api/public
 *   en astro/.env para que el menú cargue de TU Flask (slugs locales).
 */
const API_BASE = import.meta.env.PUBLIC_MENU_API_URL || 'https://velzia.shop/api/public';
const API_KEY = import.meta.env.SERVICE_API_KEY || '';

function headers(): Record<string, string> {
  const h: Record<string, string> = {};
  if (API_KEY) h['x-api-key'] = API_KEY;
  return h;
}

export async function fetchMenu(slug: string): Promise<MenuResponse> {
  const res = await fetch(`${API_BASE}/menu/${slug}`, { headers: headers() });
  if (!res.ok) {
    throw new Error(`Failed to fetch menu: ${res.status}`);
  }
  return res.json();
}

export async function fetchCategory(slug: string, categoryId: number): Promise<{
  success: boolean;
  data: { category: Category; products: Product[] };
}> {
  const res = await fetch(`${API_BASE}/menu/${slug}/categoria/${categoryId}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to fetch category: ${res.status}`);
  return res.json();
}

export async function fetchNovedades(
  slug: string,
  page = 1,
  perPage = 12
): Promise<{
  success: boolean;
  data: { products: Product[]; pagination: { page: number; per_page: number; total: number; pages: number } };
}> {
  const res = await fetch(`${API_BASE}/menu/${slug}/novedades?page=${page}&per_page=${perPage}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to fetch novedades: ${res.status}`);
  return res.json();
}

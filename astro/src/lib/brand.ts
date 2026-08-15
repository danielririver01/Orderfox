/**
 * brand.ts — Resolución del brand_color del restaurante en el frontend.
 *
 * El color de marca del restaurante solo se aplica a:
 *  - botones primarios (agregar al pedido, ver pedido)
 *  - el precio del producto
 *  - la categoría activa (pill / sidebar)
 *
 * Contraste (WCAG):
 *  - Si el color + texto oscuro (#1A120A) cumple 4.5:1 → texto oscuro.
 *  - Si no, y el color + crema (#F5EFE7) cumple 4.5:1 → texto crema.
 *  - Si ninguno cumple, o el hex es inválido/nulo → fallback #FF7A29.
 */

export interface BrandColors {
  color: string;
  ink: string;
}

export const BRAND_FALLBACK = '#FF7A29';
export const BRAND_INK_DARK = '#1A120A';
export const BRAND_INK_CREAM = '#F5EFE7';
export const DEFAULT_COVER =
  'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=1600&auto=format&fit=crop';

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

function luminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const ra = hexToRgb(a);
  const rb = hexToRgb(b);
  if (!ra || !rb) return 0;
  const la = luminance(ra);
  const lb = luminance(rb);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

export function resolveBrandColor(hex: string | null | undefined): BrandColors {
  if (!hex) return { color: BRAND_FALLBACK, ink: BRAND_INK_DARK };
  const c = hex.trim();
  if (!/^#[0-9A-Fa-f]{6}$/.test(c)) return { color: BRAND_FALLBACK, ink: BRAND_INK_DARK };

  if (contrastRatio(c, BRAND_INK_DARK) >= 4.5) return { color: c, ink: BRAND_INK_DARK };
  if (contrastRatio(c, BRAND_INK_CREAM) >= 4.5) return { color: c, ink: BRAND_INK_CREAM };
  return { color: BRAND_FALLBACK, ink: BRAND_INK_DARK };
}

export function applyBrand(hex: string | null | undefined): void {
  const { color, ink } = resolveBrandColor(hex);
  const root = document.documentElement;
  root.style.setProperty('--brand', color);
  root.style.setProperty('--brand-ink', ink);
}

/** Portada del menú: backend ya la resuelve; fallback para backend viejo. */
export function menuCover(cover: string | null | undefined): string {
  return cover && cover.trim() ? cover.trim() : DEFAULT_COVER;
}

/**
 * Banco de imágenes por categoría (Unsplash, libres, images.unsplash.com).
 * Se usa como fallback cuando un producto no tiene foto propia, de forma que
 * el menú nunca muestra un placeholder vacío ni una letra inicial.
 * Las claves están normalizadas (minúsculas, sin tildes, espacios simples).
 */
export const PRODUCT_IMAGE_BANK: Record<string, string> = {
  desayunos: 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?q=80&w=800&auto=format&fit=crop',
  'sopas y sancochos': 'https://images.unsplash.com/photo-1672300389082-540b049e4786?q=80&w=800&auto=format&fit=crop',
  'platos tipicos': 'https://images.unsplash.com/photo-1723693407562-bb4fcae76797?q=80&w=800&auto=format&fit=crop',
  'fritos y mecatos': 'https://images.unsplash.com/photo-1769254870299-338bfd99aabd?q=80&w=800&auto=format&fit=crop',
  parrilla: 'https://images.unsplash.com/photo-1562625964-ffe9b2f617fc?q=80&w=800&auto=format&fit=crop',
  mariscos: 'https://images.unsplash.com/photo-1694685367640-05d6624e57f1?q=80&w=800&auto=format&fit=crop',
  ensaladas: 'https://images.unsplash.com/photo-1600335895229-6e75511892c8?q=80&w=800&auto=format&fit=crop',
  postres: 'https://images.unsplash.com/photo-1532556660262-1c45d5fae825?q=80&w=800&auto=format&fit=crop',
  'bebidas frias': 'https://images.unsplash.com/photo-1523677011781-c91d1bbe2f9e?q=80&w=800&auto=format&fit=crop',
  'bebidas calientes': 'https://images.unsplash.com/photo-1647919234555-3d06e2c923f4?q=80&w=800&auto=format&fit=crop',
  cocteles: 'https://images.unsplash.com/photo-1589132971214-ed8169976abd?q=80&w=800&auto=format&fit=crop',
  cervezas: 'https://images.unsplash.com/photo-1618183479302-1e0aa382c36b?q=80&w=800&auto=format&fit=crop',
};

/** Fallback último: mesa con platos (comida colombiana). Nunca se muestra una letra. */
export const GENERAL_PRODUCT_IMAGE =
  'https://images.unsplash.com/photo-1731090390538-d814c9925232?q=80&w=800&auto=format&fit=crop';

/** Normaliza un nombre de categoría: minúsculas, sin tildes, espacios simples. */
export function normalizeCategory(name: string | null | undefined): string {
  return (name || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ');
}

/**
 * Palabras clave para resolver categorías reales que no son exactas al banco
 * (ej. "Desayunos Típicos" → desayunos, "Patacones Fritos" → fritos y mecatos).
 * El orden importa: las más específicas primero.
 */
const CATEGORY_KEYWORDS: Array<[RegExp, string]> = [
  [/desayun/, 'desayunos'],
  [/sopas|sancoch/, 'sopas y sancochos'],
  [/plato/, 'platos tipicos'],
  [/frito|mecato|patacon/, 'fritos y mecatos'],
  [/parrill|asado|grill/, 'parrilla'],
  [/marisc|pescad|ceviche/, 'mariscos'],
  [/ensalad/, 'ensaladas'],
  [/postre|dulce/, 'postres'],
  [/bebida|refresco|jugo/, 'bebidas frias'],
  [/cafe|caliente|chocolate|tinto/, 'bebidas calientes'],
  [/coctel|trago/, 'cocteles'],
  [/cerveza/, 'cervezas'],
];

/**
 * Resuelve la imagen de un producto: foto propia → banco por categoría → general.
 * Nunca devuelve null ni un string vacío, garantizando que el menú siempre
 * muestre una imagen real.
 */
export function productImage(imageUrl: string | null | undefined, categoryName?: string | null): string {
  if (imageUrl && imageUrl.trim()) return imageUrl.trim();
  const key = normalizeCategory(categoryName);
  if (PRODUCT_IMAGE_BANK[key]) return PRODUCT_IMAGE_BANK[key];
  for (const [re, target] of CATEGORY_KEYWORDS) {
    if (re.test(key)) return PRODUCT_IMAGE_BANK[target];
  }
  return GENERAL_PRODUCT_IMAGE;
}

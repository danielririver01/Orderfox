import type { CartItem, Product, Modifier } from './types';

const CART_PREFIX = 'velziaCart_';

function getKey(restaurantId: number): string {
  return `${CART_PREFIX}${restaurantId}`;
}

interface StoredItem {
  productId: number;
  productName: string;
  productPrice: number;
  productImage: string | null;
  quantity: number;
  modifierIds: number[];
  modifierNames: string[];
  modifierPrice: number;
}

const TTL = 24 * 60 * 60 * 1000;

export function loadCart(restaurantId: number): CartItem[] {
  try {
    const raw = localStorage.getItem(getKey(restaurantId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    const age = Date.now() - parsed.timestamp;
    if (age > TTL) {
      localStorage.removeItem(getKey(restaurantId));
      return [];
    }
    return parsed.items || [];
  } catch {
    return [];
  }
}

export function saveCart(restaurantId: number, items: CartItem[]): void {
  const data = {
    timestamp: Date.now(),
    items,
  };
  localStorage.setItem(getKey(restaurantId), JSON.stringify(data));
}

export function clearCart(restaurantId: number): void {
  localStorage.removeItem(getKey(restaurantId));
}

export function getCartTotal(restaurantId: number): number {
  const items = loadCart(restaurantId);
  return items.reduce((sum, item) => {
    const extras = item.selectedModifiers.reduce((m, mod) => m + mod.extra_price, 0);
    return sum + (item.product.price + extras) * item.quantity;
  }, 0);
}

export function getCartCount(restaurantId: number): number {
  const items = loadCart(restaurantId);
  return items.reduce((sum, item) => sum + item.quantity, 0);
}

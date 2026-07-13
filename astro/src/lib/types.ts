export interface Restaurant {
  id: number;
  name: string;
  slug: string;
  whatsapp_phone: string;
  is_open: boolean;
  ordering_disabled: boolean;
}

export interface Modifier {
  id: number;
  name: string;
  extra_price: number;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  price: number;
  image_url: string | null;
  modifiers: Modifier[];
}

export interface Category {
  id: number;
  name: string;
  image_url: string | null;
  product_count: number;
  products: Product[];
}

export interface MenuData {
  restaurant: Restaurant;
  categories: Category[];
}

export interface MenuResponse {
  success: boolean;
  data: MenuData;
}

export interface CartItem {
  product: Product;
  quantity: number;
  selectedModifiers: Modifier[];
}

export interface OrderResult {
  success: boolean;
  order_number: string;
  order_id: number;
  total: number;
  items: { name: string; qty: number; extras: string[] }[];
  customer_name: string;
  address_full: string | null;
  table_name: string | null;
}

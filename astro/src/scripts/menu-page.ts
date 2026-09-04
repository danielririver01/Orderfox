/**
 * menu-page.ts — Lógica del menú público (Astro).
 * Se invoca desde [slug]/index.astro con los datos incrustados en #page-data.
 */
import { applyBrand } from '../lib/brand';
import type { Product } from '../lib/types';

export interface PageData {
  productsMap: Record<string, Product>;
  fallbackImages?: Record<string, string>;
  restaurantId: number;
  whatsappPhone: string;
  tableId: string | number | null;
  brandColor?: string | null;
  ordering: boolean;
}

export function initMenuPage(data: PageData): void {
  applyBrand(data.brandColor);

  // Altura del header sticky (compensa pills/sidebar y scroll-margin)
  const header = document.getElementById('menu-header');
  if (header) {
    const setHeaderH = (): void => {
      document.documentElement.style.setProperty('--header-h', `${header.offsetHeight}px`);
    };
    setHeaderH();
    window.addEventListener('resize', setHeaderH);
  }

  const PRODUCTS_MAP = data.productsMap;
  const RESTAURANT_ID = data.restaurantId;

  const detailPanel = document.getElementById('product-detail');
  const closeBtn = document.getElementById('close-detail');
  const addBtn = document.getElementById('add-to-cart');
  const detailName = document.getElementById('detail-name');
  const detailDesc = document.getElementById('detail-description');
  const detailPrice = document.getElementById('detail-price');
  const detailImg = document.getElementById('detail-image') as HTMLImageElement | null;
  const detailImgPlaceholder = document.getElementById('detail-image-placeholder');
  const detailModSection = document.getElementById('detail-modifiers-section');
  const modifiersList = document.getElementById('modifiers-list');
  const qtyDisplay = document.getElementById('qty-display');
  const qtyMinus = document.getElementById('qty-minus');
  const qtyPlus = document.getElementById('qty-plus');

  let currentProductId: number | null = null;
  let currentQty = 1;

  // ── Cart helpers ──
  function loadCart(): any[] {
    try {
      const raw = localStorage.getItem('velziaCart_' + RESTAURANT_ID);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return parsed.items || [];
    } catch {
      return [];
    }
  }

  function saveCart(items: any[]): void {
    const dataStore = { timestamp: Date.now(), items };
    localStorage.setItem('velziaCart_' + RESTAURANT_ID, JSON.stringify(dataStore));
    document.dispatchEvent(new CustomEvent('cart-updated'));
  }

  function showToast(msg: string, type: 'success' | 'error' | 'info' = 'info'): void {
    if (typeof (window as any).showToast === 'function') {
      (window as any).showToast(msg, type);
      return;
    }
    const container = document.getElementById('toast-container');
    if (!container) return;
    const colors: Record<string, string> = {
      success: 'bg-veg text-cta-ink',
      error: 'bg-red-600 text-white',
      info: 'bg-card text-ink border border-border-subtle',
    };
    const toast = document.createElement('div');
    toast.className = 'rounded-lg px-4 py-3 text-sm font-medium shadow-lg transition-all duration-300 ' + (colors[type] || colors.info);
    toast.textContent = msg;
    container.appendChild(toast);
    window.setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      window.setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // ── Detalle de producto ──
  function openDetail(productId: number): void {
    const product = PRODUCTS_MAP[productId];
    if (!product) return;

    currentProductId = product.id;
    currentQty = 1;
    if (qtyDisplay) qtyDisplay.textContent = '1';

    if (detailName) detailName.textContent = product.name;
    if (detailDesc) detailDesc.textContent = product.description || '';
    if (detailPrice) detailPrice.textContent = '$' + product.price.toLocaleString('es-CO');

    const fallbackImages = data.fallbackImages || {};
    const imgSrc = product.image_url || fallbackImages[String(product.id)];
    if (imgSrc) {
      if (detailImg) {
        detailImg.src = imgSrc;
        detailImg.alt = product.name;
        detailImg.classList.remove('hidden');
      }
      if (detailImgPlaceholder) detailImgPlaceholder.classList.add('hidden');
    } else {
      if (detailImg) detailImg.classList.add('hidden');
      if (detailImgPlaceholder) {
        detailImgPlaceholder.textContent = product.name.charAt(0);
        detailImgPlaceholder.classList.remove('hidden');
      }
    }

    if (addBtn) addBtn.setAttribute('data-product-id', String(product.id));

    if (detailModSection && modifiersList) {
      if (product.modifiers && product.modifiers.length > 0) {
        detailModSection.style.display = '';
        modifiersList.innerHTML = product.modifiers.map((mod) => `
          <label class="flex cursor-pointer items-center gap-3 rounded-xl border border-border-subtle bg-card-hover p-3 transition hover:bg-card">
            <input type="checkbox" value="${mod.id}" data-mod-name="${mod.name}" data-mod-price="${mod.extra_price}" class="h-4 w-4 rounded border-white/20 bg-card text-accent" />
            <span class="flex-1 text-sm text-ink">${mod.name}</span>
            ${mod.extra_price > 0 ? `<span class="text-xs text-ink-muted">+$${mod.extra_price.toLocaleString('es-CO')}</span>` : ''}
          </label>
        `).join('');
      } else {
        detailModSection.style.display = 'none';
        modifiersList.innerHTML = '';
      }
    }

    if (detailPanel) detailPanel.classList.remove('translate-x-full');
    document.getElementById('cart-sidebar')?.classList.add('translate-x-full');
    document.getElementById('cart-overlay')?.classList.add('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeDetail(): void {
    if (detailPanel) detailPanel.classList.add('translate-x-full');
    document.body.style.overflow = '';
    currentProductId = null;
  }

  // Apertura del detalle desde cards (delegación) y botones +
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const addEl = target.closest('[data-add-id]') as HTMLElement | null;
    if (addEl) {
      if (!data.ordering) return;
      e.stopPropagation();
      const id = parseInt(addEl.getAttribute('data-add-id') || '0', 10);
      openDetail(id);
      return;
    }
    const card = target.closest('[data-product-id]') as HTMLElement | null;
    if (!card) return;
    e.stopPropagation();
    const id = parseInt(card.getAttribute('data-product-id') || '0', 10);
    openDetail(id);
  });

  document.addEventListener('open-product', ((e: CustomEvent) => {
    openDetail(e.detail.productId);
  }) as EventListener);

  if (closeBtn) closeBtn.addEventListener('click', closeDetail);

  if (qtyMinus) qtyMinus.addEventListener('click', () => {
    if (currentQty > 1) {
      currentQty--;
      if (qtyDisplay) qtyDisplay.textContent = String(currentQty);
    }
  });
  if (qtyPlus) qtyPlus.addEventListener('click', () => {
    if (currentQty < 99) {
      currentQty++;
      if (qtyDisplay) qtyDisplay.textContent = String(currentQty);
    }
  });

  if (addBtn) addBtn.addEventListener('click', () => {
    if (!data.ordering) return;
    const pid = parseInt(addBtn.getAttribute('data-product-id') || '0', 10);
    if (!pid) return;

    const product = PRODUCTS_MAP[pid];
    if (!product) return;

    const modifierCheckboxes = modifiersList ? modifiersList.querySelectorAll('input[type="checkbox"]:checked') : [];
    const selectedModifiers = Array.from(modifierCheckboxes).map((cb) => {
      const val = parseInt((cb as HTMLInputElement).value, 10);
      const mod = (product.modifiers || []).find((m) => m.id === val);
      return mod || {
        id: val,
        name: cb.getAttribute('data-mod-name') || '',
        extra_price: parseInt(cb.getAttribute('data-mod-price') || '0', 10),
      };
    });

    const items = loadCart();
    const modifierIds = selectedModifiers.map((m) => m.id).sort();
    const existingIdx = items.findIndex((item: any) => {
      if (item.product.id !== product.id) return false;
      const itemModIds = (item.selectedModifiers || []).map((m: any) => m.id).sort();
      if (itemModIds.length !== modifierIds.length) return false;
      return modifierIds.every((id, i) => id === itemModIds[i]);
    });

    if (existingIdx >= 0) {
      items[existingIdx].quantity += currentQty;
    } else {
      items.push({ product, quantity: currentQty, selectedModifiers });
    }

    saveCart(items);
    showToast('Producto agregado al pedido', 'success');
    closeDetail();
    if (addBtn) {
      const originalText = addBtn.textContent;
      addBtn.classList.remove('btn-primary');
      addBtn.classList.add('bg-veg');
      addBtn.style.color = '#1A120A';
      addBtn.textContent = '✓ Agregado';
      window.setTimeout(() => {
        addBtn.classList.add('btn-primary');
        addBtn.classList.remove('bg-veg');
        addBtn.style.color = '';
        addBtn.textContent = originalText;
      }, 1500);
    }
  });

  // ── Búsqueda ──
  const noResults = document.getElementById('no-results');
  const searchInputs = Array.from(document.querySelectorAll<HTMLInputElement>('.search-input'));
  searchInputs.forEach((input) => {
    input.addEventListener('input', (e) => {
      const q = (e.target as HTMLInputElement).value.toLowerCase().trim();
      const sections = Array.from(document.querySelectorAll<HTMLElement>('section[id^="cat-"]'));
      let totalVisible = 0;
      sections.forEach((section) => {
        const cards = Array.from(section.querySelectorAll<HTMLElement>('[data-product-id]'));
        let visibleCount = 0;
        cards.forEach((card) => {
          const name = (card.querySelector('h3') as HTMLElement)?.textContent?.toLowerCase() || '';
          const desc = (card.querySelector('p') as HTMLElement)?.textContent?.toLowerCase() || '';
          const match = !q || name.includes(q) || desc.includes(q);
          card.style.display = match ? '' : 'none';
          if (match) visibleCount++;
        });
        section.style.display = visibleCount === 0 ? 'none' : '';
        totalVisible += visibleCount;
      });
      if (noResults) noResults.classList.toggle('hidden', totalVisible > 0);
    });
  });

  // ── Scroll-spy + navegación por categorías ──
  const navItems = Array.from(document.querySelectorAll<HTMLElement>('[data-nav-item]'));
  const sections = Array.from(document.querySelectorAll<HTMLElement>('section[id^="cat-"]'));
  let suppressSpy = false;
  let suppressTimer: number | undefined;

  function setActive(id: number | null): void {
    navItems.forEach((item) => {
      const isActive = item.getAttribute('data-nav-id') === String(id);
      if (item.closest('[data-nav-mode="pills"]')) {
        item.classList.toggle('nav-pill-active', isActive);
        if (isActive) {
          item.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        }
      } else {
        item.classList.toggle('nav-side-active', isActive);
      }
    });
  }

  if ('IntersectionObserver' in window && sections.length > 0) {
    const observer = new IntersectionObserver((entries) => {
      if (suppressSpy) return;
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (visible.length === 0) return;
      const sec = visible[0].target as HTMLElement;
      setActive(parseInt(sec.id.replace('cat-', ''), 10));
    }, {
      threshold: 0.3,
      rootMargin: '-15% 0px -35% 0px',
    });
    sections.forEach((s) => observer.observe(s));
  }

  navItems.forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const id = link.getAttribute('href')?.slice(1);
      if (!id) return;
      const target = document.getElementById(id);
      if (!target) return;
      suppressSpy = true;
      if (suppressTimer) window.clearTimeout(suppressTimer);
      suppressTimer = window.setTimeout(() => {
        suppressSpy = false;
      }, 800);
      setActive(parseInt(id.replace('cat-', ''), 10));
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  // ── Deep link: #product-XXX ──
  const hash = window.location.hash;
  if (hash && hash.startsWith('#product-')) {
    const id = hash.split('-')[1];
    const card = document.querySelector(`[data-product-id="${id}"]`) as HTMLElement | null;
    if (card) {
      window.setTimeout(() => {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        card.style.borderColor = 'var(--brand)';
        card.style.boxShadow = '0 0 0 2px var(--brand)';
        window.setTimeout(() => {
          card.style.borderColor = '';
          card.style.boxShadow = '';
        }, 2500);
      }, 500);
    }
  }
}
/*
 * POS Velzia Verduras — vanilla JS (convención del repo: JS separado).
 * Flujo del verdulero: tocar producto → ajustar cantidad (gramo) → cobrar
 * → ticket imprimible. La venta va por sesión (cookie), nunca con la
 * SERVICE_API_KEY.
 */
(function () {
  'use strict';

  const PRICES = JSON.parse(document.getElementById('pos-data').textContent);
  const POS_URLS = window.POS_URLS;
  const CSRF_TOKEN = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  function fmtCop(n) {
    return '$' + Number(n).toLocaleString('es-CO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function roundGrams(n) {
    return Math.round(n * 1000) / 1000;
  }

  // ── Estado del carrito ──────────────────────────────────────
  const cart = new Map(); // product_id → {id, name, unit, price, qty, ...}

  function cartItems() { return Array.from(cart.values()); }

  function cartTotal() {
    return cartItems().reduce((sum, it) => sum + it.price * it.qty, 0);
  }

  function removeItem(id) {
    cart.delete(id);
    sync();
  }

  // ── Render: barra del carrito ───────────────────────────────

  function renderCartBar() {
    const bar = $('#cart-bar');
    if (!bar) return;
    bar.hidden = cart.size === 0;
    $('#cart-count').textContent = cartItems().length + ' productos';
    $('#cart-total').textContent = fmtCop(cartTotal());
    const drawerTotal = $('#cart-drawer-total');
    if (drawerTotal) drawerTotal.textContent = fmtCop(cartTotal());
  }

  // ── Render: drawer del carrito ──────────────────────────────

  function renderCartDrawer() {
    const list = $('#cart-items');
    if (!list) return;
    list.innerHTML = '';
    cartItems().forEach((it) => {
      const row = document.createElement('div');
      row.className = 'cart-item';
      row.innerHTML = `
        <div class="cart-item-info">
          <span class="cart-item-name"></span>
          <span class="cart-item-sub"></span>
        </div>
        <div class="qty-stepper">
          <button type="button" data-act="dec" aria-label="Restar">−</button>
          <input type="number" min="0.001" step="${it.unit === 'unidad' ? 1 : 0.001}"
                 value="${it.qty}" aria-label="Cantidad de ${it.name}">
          <button type="button" data-act="inc" aria-label="Sumar">+</button>
        </div>
        <div class="cart-item-total"></div>
      `;
      row.querySelector('.cart-item-name').textContent = it.name;
      row.querySelector('.cart-item-sub').textContent =
        fmtCop(it.price) + ' / ' + it.unit;
      row.querySelector('.cart-item-total').textContent =
        fmtCop(it.price * it.qty);

      const input = row.querySelector('input');
      input.addEventListener('change', () => {
        const v = parseFloat(input.value);
        if (isNaN(v) || v <= 0) { removeItem(it.id); return; }
        it.qty = it.unit === 'unidad' ? Math.max(1, Math.round(v)) : roundGrams(v);
        sync();
      });
      row.querySelector('[data-act="dec"]').addEventListener('click', () => {
        if (it.unit === 'unidad') {
          it.qty -= 1;
          if (it.qty < 1) { removeItem(it.id); return; }
        } else {
          it.qty = roundGrams(it.qty - 0.05);
          if (it.qty <= 0) { removeItem(it.id); return; }
        }
        sync();
      });
      row.querySelector('[data-act="inc"]').addEventListener('click', () => {
        it.qty = it.unit === 'unidad' ? it.qty + 1 : roundGrams(it.qty + 0.05);
        sync();
      });

      // Botón "Leer báscula" solo en productos por peso y si el negocio
      // tiene báscula activada. El ingreso manual sigue intacto: la
      // báscula es ayuda, nunca requisito.
      if (PRICES.scale_enabled && it.unit !== 'unidad') {
        const scaleBtn = document.createElement('button');
        scaleBtn.type = 'button';
        scaleBtn.className = 'scale-btn';
        scaleBtn.title = 'Leer báscula';
        scaleBtn.setAttribute('aria-label',
          'Leer peso de la báscula para ' + it.name);
        scaleBtn.innerHTML =
          '<span class="material-symbols-rounded" aria-hidden="true">scale</span>';
        scaleBtn.addEventListener('click', () => readScale(it, scaleBtn));
        row.querySelector('.qty-stepper').appendChild(scaleBtn);
      }

      list.appendChild(row);
    });
  }

  function sync() {
    renderCartBar();
    renderCartDrawer();
  }

  // ── Render: grid de productos ───────────────────────────────

  function currentCat() {
    const active = $('.cat-pill.active');
    return active ? Number(active.dataset.catId || 0) : null;
  }

  function renderProductGrid(filterText, categoryId) {
    const grid = $('#product-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const text = (filterText || '').trim().toLowerCase();
    const visible = PRICES.products.filter((p) => {
      const matchText = !text || p.name.toLowerCase().includes(text);
      const matchCat = !categoryId || p.category_id === categoryId;
      return matchText && matchCat;
    });
    if (visible.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'cart-hint';
      empty.style.padding = '0 1rem';
      empty.textContent = 'Ningún producto coincide con la búsqueda.';
      grid.appendChild(empty);
      return;
    }
    visible.forEach((p) => {
      grid.appendChild(renderProductCard(p));
    });
  }

  const ALERT_BADGES = {
    low: { cls: 'badge-warn', icon: 'warning', text: 'Queda poco' },
    out: { cls: 'badge-danger', icon: 'error', text: 'Agotado' },
  };

  function renderProductCard(p) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'product-card';
    btn.dataset.productId = p.id;
    btn.innerHTML = `
      <span class="product-name"></span>
      <span class="product-meta">
        <span class="product-price"></span>
        <span class="product-unit"></span>
      </span>
    `;
    btn.querySelector('.product-name').textContent = p.name;
    btn.querySelector('.product-price').textContent = fmtCop(p.price);
    btn.querySelector('.product-unit').textContent = '/ ' + p.unit;

    // Alerta de rotación (Semana 5): badge informativo, siempre icono +
    // texto (nunca solo color) — la venta sigue funcionando igual.
    const alert = PRICES.alerts && PRICES.alerts[String(p.id)];
    const badge = ALERT_BADGES[alert];
    if (badge) {
      const el = document.createElement('span');
      el.className = 'badge ' + badge.cls + ' product-alert';
      el.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true"></span>';
      const label = document.createElement('span');
      label.textContent = badge.text;
      el.setAttribute('aria-label',
        badge.text + ': ' + p.name); // accesible (no depende del color)
      el.querySelector('.material-symbols-rounded').textContent = badge.icon;
      el.appendChild(label);
      btn.appendChild(el);
    }
    return btn;
  }

  function addToCart(id) {
    const p = PRICES.products.find((x) => String(x.id) === String(id));
    if (!p) return;
    const existing = cart.get(Number(id));
    const step = p.unit === 'unidad' ? 1 : 0.5;
    if (existing) {
      existing.qty = roundGrams(existing.qty + step);
    } else {
      cart.set(Number(id), {
        id: Number(id),
        name: p.name,
        unit: p.unit,
        price: Number(p.price),
        qty: step,
      });
    }
    sync();
    pulseCart();
  }

  function pulseCart() {
    const bar = $('#cart-bar');
    if (!bar) return;
    bar.classList.remove('cart-pulse');
    void bar.offsetWidth; // reinicia la animación
    bar.classList.add('cart-pulse');
  }

  // ── Báscula digital (Semana 4) ──────────────────────────────

  const KG_PER_LB = 0.45359237;
  let scaleBusy = false;

  // La báscula reporta kg; la cantidad del carrito va en la unidad del
  // producto (kg | lb). 'unidad' nunca usa báscula.
  function weightToQty(weightKg, unit) {
    if (unit === 'lb') return roundGrams(weightKg / KG_PER_LB);
    return roundGrams(weightKg);
  }

  async function readScale(item, btn) {
    if (scaleBusy) return;
    scaleBusy = true;
    btn.classList.add('reading');
    btn.disabled = true;
    try {
      const res = await fetch(POS_URLS.scale);
      const json = await res.json();
      if (!res.ok || !json.success) {
        showToast(json.error || 'No se pudo leer la báscula — teclea el peso');
        return;
      }
      item.qty = weightToQty(json.data.weight_kg, item.unit);
      sync();
      pulseCart();
    } catch (err) {
      showToast('Sin conexión — teclea el peso');
    } finally {
      scaleBusy = false;
      btn.classList.remove('reading');
      btn.disabled = false;
    }
  }

  // ── Cobro ───────────────────────────────────────────────────

  async function checkout() {
    if (cart.size === 0) return;
    const btn = $('#checkout-btn');
    btn.disabled = true;
    try {
      const res = await fetch(POS_URLS.sell, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CSRF_TOKEN,
        },
        body: JSON.stringify({
          items: cartItems().map((it) => ({
            product_id: it.id,
            quantity: it.unit === 'unidad' ? Math.round(it.qty) : it.qty,
          })),
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        showToast(json.error || 'No se pudo registrar la venta');
        return;
      }
      showTicket(json.data);
      cart.clear();
      sync();
    } catch (err) {
      showToast('Sin conexión con el servidor');
    } finally {
      btn.disabled = false;
    }
  }

  function showTicket(sale) {
    $('#ticket-number').textContent = sale.sale_number;
    const body = $('#ticket-items');
    body.innerHTML = '';
    sale.items.forEach((it) => {
      const tr = document.createElement('tr');
      const tdName = document.createElement('td');
      tdName.textContent = it.name + ' — ' + it.qty + ' ' + it.unit;
      const tdTotal = document.createElement('td');
      tdTotal.textContent = it.line_total;
      tr.appendChild(tdName);
      tr.appendChild(tdTotal);
      body.appendChild(tr);
    });
    $('#ticket-total').textContent = sale.total;
    $('#ticket-modal').classList.add('show');
  }

  function closeTicket() {
    $('#ticket-modal').classList.remove('show');
  }

  function ticketIsOpen() {
    return $('#ticket-modal').classList.contains('show');
  }

  function showToast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  // ── Drawer: abrir/cerrar ────────────────────────────────────

  function openCart() {
    $('#cart-drawer').classList.add('show');
    $('#cart-overlay').classList.add('show');
  }

  function closeCart() {
    $('#cart-drawer').classList.remove('show');
    $('#cart-overlay').classList.remove('show');
  }

  // ── Wire-up inicial ─────────────────────────────────────────

  function wireUp() {
    const search = $('#search-input');
    if (search) {
      search.addEventListener('input', (e) => {
        renderProductGrid(e.target.value, currentCat());
      });
    }

    $$('.cat-pill').forEach((pill) => {
      pill.addEventListener('click', () => {
        $$('.cat-pill').forEach((x) => x.classList.remove('active'));
        pill.classList.add('active');
        renderProductGrid($('#search-input').value, currentCat());
      });
    });

    $('#product-grid').addEventListener('click', (e) => {
      const card = e.target.closest('.product-card');
      if (card) addToCart(card.dataset.productId);
    });

    $('#cart-open-btn').addEventListener('click', openCart);
    $('#cart-close-btn').addEventListener('click', closeCart);
    $('#cart-overlay').addEventListener('click', closeCart);
    $('#checkout-btn').addEventListener('click', checkout);
    $('#ticket-close-btn').addEventListener('click', closeTicket);
    $('#ticket-print-btn').addEventListener('click', () => window.print());

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeCart(); closeTicket(); }
      if (e.key === 'Enter' && ticketIsOpen()) {
        closeTicket(); // Enter = siguiente cliente (flujo rápido de POS)
      }
    });

    renderProductGrid('', null);
    sync();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();

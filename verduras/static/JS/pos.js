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

  // ── Impresión térmica (rollo 80mm) ──────────────────────────
  // El diálogo de impresión no sabe que es un ticket: por defecto saldría
  // una hoja carta con márgenes. data-print-target marca el nodo a
  // imprimir; aquí lo clonamos a un wrapper .print-buffer (pos.css lo
  // deja a 80mm con @page margin:0) y el resto de la página se oculta.
  function printNode(node) {
    if (!node) return;
    const buffer = document.createElement('div');
    buffer.className = 'print-buffer';
    buffer.appendChild(node.cloneNode(true));
    document.body.appendChild(buffer);
    document.body.classList.add('print-data');
    window.print();
    // El diálogo de impresión bloquea; al volver, se desmonta el buffer.
    document.body.classList.remove('print-data');
    buffer.remove();
  }

  function printTicketModal() {
    printNode(document.querySelector('[data-print-target]'));
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

  // Marca visible de selección: la tarjeta queda resaltada mientras su
  // producto esté en el ticket (el dueño pedía "que se marque").
  function renderCartMarks() {
    $$('#product-grid .product-card').forEach((card) => {
      card.classList.toggle('in-cart', cart.has(Number(card.dataset.productId)));
    });
  }

  function sync() {
    renderCartBar();
    renderCartDrawer();
    renderCartMarks();
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
    // Dos vacíos distintos (decisión dueño): catálogo sin productos →
    // mensaje propio con CTA (deshabilitado hasta que exista Inventario);
    // filtro/búsqueda sin resultados → mensaje de búsqueda.
    if (PRICES.products.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-catalog';
      empty.innerHTML = `
        <span class="material-symbols-rounded" aria-hidden="true">inventory_2</span>
        <p><strong>Aún no hay productos en tu catálogo.</strong><br>Agrega tu primer producto para empezar a vender.</p>
      `;
      const cta = document.createElement('button');
      cta.type = 'button';
      cta.className = 'btn btn-primary';
      cta.disabled = true;
      cta.title = 'Próximamente: gestión de catálogo en Inventario';
      cta.textContent = 'Agregar producto · Próximamente';
      empty.appendChild(cta);
      grid.appendChild(empty);
      return;
    }
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

  // Icono honesto por unidad (sin fotos inventadas ni URLs externas:
  // el catálogo aún no tiene imágenes; el tile es tinta suave + icono).
  function unitIcon(unit) {
    return (unit === 'kg' || unit === 'g' || unit === 'lb') ? 'scale' : 'shopping_basket';
  }

  // Opción A (dueño): la tarjeta de un producto POR PESO no agrega a
  // ciegas — se expande ahí mismo con input de peso + báscula + agregar.
  // Unidad sigue siendo un toque = 1 al ticket (no hay nada que pesar).
  function renderProductCard(p) {
    const weighed = p.unit !== 'unidad';
    const card = document.createElement('div');
    card.className = 'product-card' + (weighed ? ' is-weighed' : '');
    card.dataset.productId = p.id;
    card.innerHTML = `
      <button type="button" class="product-main" aria-label="Agregar ${p.name}">
        <span class="product-top"><span class="unit-chip"></span></span>
        <span class="product-photo"><span class="material-symbols-rounded" aria-hidden="true"></span></span>
        <span class="product-name"></span>
        <span class="product-meta">
          <span class="product-price"></span>
          <span class="product-unit"></span>
        </span>
        <span class="product-foot"><span class="product-add"><span class="material-symbols-rounded" aria-hidden="true">${weighed ? 'scale' : 'add'}</span></span></span>
      </button>
    `;
    card.querySelector('.unit-chip').textContent = '$/' + String(p.unit).toUpperCase();
    card.querySelector('.product-photo .material-symbols-rounded').textContent = unitIcon(p.unit);
    card.querySelector('.product-name').textContent = p.name;
    card.querySelector('.product-price').textContent = fmtCop(p.price);
    card.querySelector('.product-unit').textContent = '/ ' + p.unit;

    const mainBtn = card.querySelector('.product-main');
    if (!weighed) {
      mainBtn.addEventListener('click', () => addToCart(p.id));
    } else {
      mainBtn.addEventListener('click', () => toggleWeighEditor(card, p));
    }

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
      card.appendChild(el);
    }
    return card;
  }

  // Editor de peso inline (opción A): la tarjeta se expande, María escribe
  // o lee la báscula y confirma. Nada se agrega hasta confirmar.
  function toggleWeighEditor(card, p) {
    const open = card.querySelector('.weigh-editor');
    if (open) {
      open.remove();
      card.classList.remove('expanded');
      return;
    }
    $$('.weigh-editor').forEach((e) => e.remove());
    $$('.product-card.expanded').forEach((c) => c.classList.remove('expanded'));
    const ed = document.createElement('div');
    ed.className = 'weigh-editor';
    ed.innerHTML = `
      <label class="weigh-label">¿Cuántos ${p.unit}?
        <input inputmode="decimal" value="0.5" aria-label="Peso en ${p.unit} de ${p.name}">
      </label>
      ${PRICES.scale_enabled ? '<button type="button" class="weigh-scale" title="Leer báscula" aria-label="Leer báscula"><span class="material-symbols-rounded" aria-hidden="true">scale</span></button>' : ''}
      <button type="button" class="weigh-add">Agregar</button>
    `;
    const input = ed.querySelector('input');
    const scaleBtn = ed.querySelector('.weigh-scale');
    const confirm = () => {
      const v = parseFloat(String(input.value).replace(',', '.'));
      if (isNaN(v) || v <= 0) {
        showToast('Escribe un peso mayor a 0');
        input.focus();
        return;
      }
      addToCart(p.id, roundGrams(v));
      ed.remove();
      card.classList.remove('expanded');
    };
    if (scaleBtn) {
      scaleBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (scaleBusy) return;
        scaleBusy = true;
        scaleBtn.disabled = true;
        try {
          const res = await fetch(POS_URLS.scale);
          const json = await res.json();
          if (!res.ok || !json.success) {
            showToast(json.error || 'No se pudo leer la báscula — teclea el peso');
            return;
          }
          input.value = weightToQty(json.data.weight_kg, p.unit);
          input.focus();
        } catch (err) {
          showToast('Sin conexión — teclea el peso');
        } finally {
          scaleBusy = false;
          scaleBtn.disabled = false;
        }
      });
    }
    ed.querySelector('.weigh-add').addEventListener('click', (e) => {
      e.stopPropagation();
      confirm();
    });
    input.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') confirm();
      if (e.key === 'Escape') {
        ed.remove();
        card.classList.remove('expanded');
      }
    });
    input.addEventListener('click', (e) => e.stopPropagation());
    card.appendChild(ed);
    card.classList.add('expanded');
    input.focus();
    input.select();
    try {
      ed.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch (err) { /* scroll opcional */ }
  }

  function addToCart(id, qtyOverride) {
    const p = PRICES.products.find((x) => String(x.id) === String(id));
    if (!p) return;
    const step = p.unit === 'unidad' ? 1 : 0.5;
    let add = step;
    if (qtyOverride !== undefined && qtyOverride !== null) {
      add = p.unit === 'unidad'
        ? Math.max(1, Math.round(qtyOverride))
        : roundGrams(qtyOverride);
    }
    const existing = cart.get(Number(id));
    if (existing) {
      existing.qty = roundGrams(existing.qty + add);
    } else {
      cart.set(Number(id), {
        id: Number(id),
        name: p.name,
        unit: p.unit,
        price: Number(p.price),
        qty: add,
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

  // Método de pago del ticket (v1 rediseño): lista cerrada igual que el
  // backend (PAYMENT_METHODS). Default efectivo. El ticket MUESTRA el
  // método; libreta es etiqueta sin ledger (Semana 3): jamás "saldo".
  const PAY_LABELS = {
    efectivo: 'Efectivo',
    tarjeta: 'Tarjeta',
    transferencia: 'Transferencia',
    libreta: 'Libreta',
  };
  let payMethod = 'efectivo';

  function setPayMethod(method) {
    if (!PAY_LABELS[method]) return;
    payMethod = method;
    $$('.pay-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.pay === method);
    });
    // La caja de recibido solo tiene sentido en efectivo.
    const cashBox = $('#cash-box');
    if (cashBox) cashBox.hidden = method !== 'efectivo';
    updateChange();
    // Al salir de libreta se suelta el cliente (no cruzar deudas).
    if (method !== 'libreta') clearPosClient();
    // Elegir Libreta muestra el formulario de cliente DE UNA (el dueño
    // fia al vuelo; buscar es el camino alternativo, no un requisito).
    setNewClientPane(method === 'libreta');
    renderClientPicker();
  }

  // ── Cliente de libreta (dueño): exige dueño de la deuda ──────
  let posClient = null; // {id, name}

  function clientesBase() {
    return String(POS_URLS.sell || '').replace(/\/sell$/, '');
  }

  function renderClientPicker() {
    const picker = $('#client-picker');
    if (picker) picker.hidden = payMethod !== 'libreta';
    renderClientLabel();
  }

  // Panel "crear cliente al vuelo" del drawer: visible/oculto. En libreta
  // nace visible (petición del dueño); al buscar, solo si no hay resultados.
  function setNewClientPane(show, name) {
    const pane = $('#client-new');
    if (!pane) return;
    pane.hidden = !show;
    if (show && name) {
      const input = $('#client-new-name');
      if (input) input.value = name;
    }
  }

  function renderClientLabel() {
    const label = $('#customer-label');
    if (label) {
      label.textContent = posClient ? posClient.name : 'Cliente General';
    }
  }

  function clearPosClient() {
    posClient = null;
    renderClientLabel();
  }

  async function searchClients(query) {
    const box = $('#client-results');
    if (!box) return;
    box.innerHTML = '';
    const toggleNew = (show, name) => setNewClientPane(show, name);
    if (!query) {
      // Sin query en libreta el formulario vuelve: es el estado base.
      toggleNew(payMethod === 'libreta');
      return;
    }
    let rows = [];
    try {
      const res = await fetch(
        `${clientesBase()}/clientes/buscar?q=${encodeURIComponent(query)}`);
      const json = await res.json();
      if (res.ok && json.success) rows = json.data.clientes || [];
    } catch (err) {
      rows = [];
    }
    rows.slice(0, 6).forEach((c) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'client-result';
      // saldo ya llega formateado del backend ($1.234 — _fmt_short).
      btn.textContent = `${c.name} · ${c.saldo}`;
      btn.addEventListener('click', () => {
        posClient = { id: c.id, name: c.name };
        renderClientLabel();
        box.innerHTML = '';
        toggleNew(false);
        const search = $('#client-search');
        if (search) search.value = '';
      });
      box.appendChild(btn);
    });
    toggleNew(rows.length === 0, query);
  }

  async function createPosClient() {
    const name = ($('#client-new-name') || {}).value || '';
    const phone = ($('#client-new-phone') || {}).value || '';
    if (!name.trim()) {
      showToast('Escribe el nombre del cliente');
      return;
    }
    try {
      const res = await fetch(`${clientesBase()}/clientes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CSRF_TOKEN,
        },
        body: JSON.stringify({ name: name.trim(), phone: phone.trim() }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        showToast(json.error || 'No se pudo crear el cliente');
        return;
      }
      posClient = { id: json.data.client_id, name: json.data.name };
      renderClientLabel();
      $('#client-results').innerHTML = '';
      $('#client-new').hidden = true;
      const search = $('#client-search');
      if (search) search.value = '';
      showToast(json.data.created ? 'Cliente creado' : 'Cliente elegido');
    } catch (err) {
      showToast('Sin conexión con el servidor');
    }
  }

  function cashReceived() {
    const input = $('#cash-received');
    if (!input) return null;
    const raw = String(input.value || '').trim().replace(/[.,\s]/g, '');
    if (!raw) return null;
    const v = Number(raw);
    return Number.isFinite(v) && v > 0 ? v : NaN;
  }

  function updateChange() {
    const changeEl = $('#cash-change');
    if (!changeEl) return;
    if (payMethod !== 'efectivo') {
      changeEl.textContent = '$0';
      return;
    }
    const received = cashReceived();
    if (received === null || Number.isNaN(received)) {
      changeEl.textContent = '$0';
      return;
    }
    changeEl.textContent = fmtCop(Math.max(0, received - cartTotal()));
  }

  // Refrescar vueltas al cambiar el carrito también.
  const _sync = sync;
  sync = function () {
    _sync();
    updateChange();
  };

  async function checkout() {
    if (cart.size === 0) return;
    const btn = $('#checkout-btn');
    btn.disabled = true;
    try {
      const payload = {
        items: cartItems().map((it) => ({
          product_id: it.id,
          quantity: it.unit === 'unidad' ? Math.round(it.qty) : it.qty,
        })),
        payment_method: payMethod,
      };
      if (payMethod === 'efectivo') {
        const received = cashReceived();
        if (received !== null && !Number.isNaN(received)) {
          payload.amount_received = received;
        }
        // Vacío = venta rápida sin control de recibido (válido).
      }
      if (payMethod === 'libreta') {
        if (!posClient) {
          showToast('Elige o crea el cliente para fiar');
          btn.disabled = false;
          return;
        }
        payload.client_id = posClient.id;
        payload.customer_name = posClient.name;
      }
      const res = await fetch(POS_URLS.sell, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CSRF_TOKEN,
        },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        showToast(json.error || 'No se pudo registrar la venta');
        return;
      }
      showTicket(json.data);
      cart.clear();
      const cashInput = $('#cash-received');
      if (cashInput) cashInput.value = '';
      clearPosClient();
      sync();
    } catch (err) {
      showToast('Sin conexión con el servidor');
    } finally {
      btn.disabled = false;
    }
  }

  function showTicket(sale) {
    document.body.classList.add('print-ticket');
    $('#ticket-number').textContent = sale.sale_number;
    const customerEl = $('#ticket-customer');
    if (customerEl) {
      customerEl.textContent = 'Cliente: ' + (sale.customer_name || 'Cliente General');
    }
    const methodEl = $('#ticket-method');
    if (methodEl) {
      methodEl.textContent = 'Método: ' + (PAY_LABELS[sale.payment_method] || 'Sin registro');
    }
    const receivedEl = $('#ticket-received');
    if (receivedEl) {
      if (sale.amount_received) {
        receivedEl.hidden = false;
        receivedEl.textContent = 'Recibido: ' + sale.amount_received;
      } else {
        receivedEl.hidden = true;
      }
    }
    const changeEl = $('#ticket-change');
    if (changeEl) {
      if (sale.change_due) {
        changeEl.hidden = false;
        changeEl.textContent = 'Vueltas: ' + sale.change_due;
      } else {
        changeEl.hidden = true;
      }
    }
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
    document.body.classList.remove('print-ticket');
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

    // Sin delegación global en el grid: cada tarjeta cablea lo suyo
    // (unidad agrega, peso expande editor). Delegar aquí duplicaría.
    $$('.pay-btn').forEach((b) => {
      b.addEventListener('click', () => setPayMethod(b.dataset.pay));
    });
    const cashInput = $('#cash-received');
    if (cashInput) cashInput.addEventListener('input', updateChange);
    const clientSearch = $('#client-search');
    if (clientSearch) {
      let timer = null;
      clientSearch.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => searchClients(clientSearch.value.trim()), 250);
      });
    }
    const clientSave = $('#client-new-save');
    if (clientSave) clientSave.addEventListener('click', createPosClient);
    renderClientPicker();

    const quickBtn = $('#quick-sale-btn');
    if (quickBtn) {
      quickBtn.addEventListener('click', () => {
        const search = $('#search-input');
        if (search) search.focus();
      });
    }

    $('#cart-open-btn').addEventListener('click', openCart);
    $('#cart-close-btn').addEventListener('click', closeCart);
    $('#cart-overlay').addEventListener('click', closeCart);
    $('#checkout-btn').addEventListener('click', checkout);
    $('#ticket-close-btn').addEventListener('click', closeTicket);
    $('#ticket-print-btn').addEventListener('click', printTicketModal);

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

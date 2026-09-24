/*
 * Inventario y Precios — vanilla JS (convención del repo: JS separado).
 * Filtros + precio inline + nuevo producto. Todo por sesión del POS
 * (cookie), sin roles en v1. CSRF vía meta (igual que pos.js).
 */
(function () {
  'use strict';

  const CSRF_TOKEN = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  const URLS = window.INV_URLS || {};

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  function showToast(msg) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CSRF_TOKEN,
      },
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    return { ok: res.ok, json };
  }

  // ── Filtros: texto + categoría ────────────────────────────

  function currentCat() {
    const active = $('.cat-pill.active');
    return active ? String(active.dataset.catId || '') : '';
  }

  function applyFilters() {
    const text = (($('#inv-search') || {}).value || '').trim().toLowerCase();
    const cat = currentCat();
    const rows = $$('.inv-row');
    let shown = 0;
    rows.forEach((row) => {
      const okText = !text || (row.dataset.name || '').includes(text);
      const okCat = !cat || String(row.dataset.catId || '') === cat;
      const show = okText && okCat;
      row.style.display = show ? '' : 'none';
      if (show) shown += 1;
    });
    // Sin filas (catálogo vacío) manda el estado vacío propio de la tabla,
    // no el de búsqueda: no mostrar los dos mensajes a la vez.
    const empty = $('#inv-noresults');
    if (empty) empty.hidden = rows.length === 0 || shown !== 0;
  }

  // ── Precio inline (Fase 2): clic → input → Enter/blur guarda ──

  function editPrice(cell) {
    if (cell.querySelector('input')) return;
    const row = cell.closest('.inv-row');
    const current = row.dataset.price || '';
    cell.textContent = '';
    const input = document.createElement('input');
    input.value = current;
    input.inputMode = 'decimal';
    input.setAttribute('aria-label', 'Nuevo precio');
    cell.appendChild(input);
    input.focus();
    input.select();

    let done = false;
    const commit = async (save) => {
      if (done) return;
      done = true;
      const value = input.value.trim();
      if (!save || value === current) {
        paintPrice(cell, row);
        return;
      }
      const { ok, json } = await postJson(URLS.price, {
        product_id: Number(row.dataset.productId),
        price: value,
      });
      if (!ok || !json.success) {
        showToast((json && json.error) || 'No se pudo guardar el precio');
        paintPrice(cell, row);
        return;
      }
      row.dataset.price = json.data.price;
      paintPrice(cell, row);
      showToast('Precio actualizado');
    };
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') commit(true);
      if (e.key === 'Escape') commit(false);
    });
    input.addEventListener('blur', () => commit(true));
  }

  // Formato es-CO con decimales, igual que el servidor (_fmt_cop).
  function fmtCop(n) {
    return '$' + Number(n).toLocaleString('es-CO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function paintPrice(cell, row) {
    cell.textContent = fmtCop(row.dataset.price) + ' /' + row.dataset.unit;
  }

  // ── Nuevo producto (Fase 2, sin roles) ────────────────────

  // ── Formulario lateral: crear Y editar (tercera columna en desktop
  // intercambiando con Actividad, pantalla completa en móvil). El modal
  // de edición se jubiló: un solo formulario, dos modos.
  function showFormPanel() {
    const act = $('#panel-actividad');
    if (act) act.hidden = true;
    const panel = $('#inv-create-panel');
    if (panel) {
      panel.hidden = false;
      panel.scrollIntoView({ block: 'nearest' });
    }
  }

  function closeFormPanel() {
    const panel = $('#inv-create-panel');
    if (panel) panel.hidden = true;
    const act = $('#panel-actividad');
    if (act) act.hidden = false;
  }

  function openCreate() {
    $('#inv-c-title').textContent = 'Nuevo Producto';
    const icon = $('#inv-c-icon');
    if (icon) icon.textContent = 'add_circle';
    $('#inv-c-id').value = '';
    $('#inv-c-name').value = '';
    $('#inv-c-price').value = '';
    $('#inv-c-price-wrap').hidden = false;
    $('#inv-c-unit').disabled = false;
    $('#inv-c-unit-note').hidden = true;
    // Reset total: el modo editar deja rastros (categoría nueva visible,
    // checkbox de activo). Crear siempre parte limpio.
    const catSel = $('#inv-c-cat');
    if (catSel) catSel.selectedIndex = 0;
    $('#inv-c-catnew').value = '';
    $('#inv-c-catnew-wrap').hidden = true;
    $('#inv-c-active-wrap').hidden = true;
    $('#inv-c-active').checked = true;
    showFormPanel();
    $('#inv-c-name').focus();
  }

  function openEdit(btn) {
    $('#inv-c-title').textContent = 'Editar Producto';
    const icon = $('#inv-c-icon');
    if (icon) icon.textContent = 'edit';
    $('#inv-c-id').value = btn.dataset.productId;
    $('#inv-c-name').value = btn.dataset.name || '';
    $('#inv-c-unit').value = btn.dataset.unit || 'kg';
    $('#inv-c-unit').disabled = true; // unidad jamás editable
    $('#inv-c-unit-note').hidden = false;
    const unitName = $('#inv-c-unit-name');
    if (unitName) unitName.textContent = btn.dataset.unit || 'esta unidad';
    $('#inv-c-price-wrap').hidden = true; // el precio es inline en la tabla
    const catSel = $('#inv-c-cat');
    catSel.value = btn.dataset.catId || catSel.value;
    $('#inv-c-catnew').value = '';
    $('#inv-c-catnew-wrap').hidden = true;
    $('#inv-c-active-wrap').hidden = false;
    $('#inv-c-active').checked = btn.dataset.active !== '0';
    showFormPanel();
    $('#inv-c-name').focus();
  }

  async function saveForm() {
    const btn = $('#inv-c-save');
    const editId = $('#inv-c-id').value;
    btn.disabled = true;
    try {
      const catSel = $('#inv-c-cat');
      const payload = {
        name: $('#inv-c-name').value.trim(),
        category_id: catSel.value === '__new' ? null : Number(catSel.value),
        category_name: catSel.value === '__new'
          ? $('#inv-c-catnew').value.trim() : null,
      };
      let url = URLS.product;
      if (editId) {
        payload.product_id = Number(editId);
        payload.is_active = $('#inv-c-active').checked;
        url = URLS.edit;
      } else {
        payload.unit = $('#inv-c-unit').value;
        payload.price = $('#inv-c-price').value.trim();
      }
      const { ok, json } = await postJson(url, payload);
      if (!ok || !json.success) {
        showToast((json && json.error) || 'No se pudo guardar el producto');
        return;
      }
      if (!editId && json.data && json.data.reactivated) {
        showToast(`${json.data.name} reactivado con su historial`);
        setTimeout(() => window.location.reload(), 900);
        return;
      }
      window.location.reload();
    } finally {
      btn.disabled = false;
    }
  }

  // ── Reactivar explícito (P3): visible y predecible, nada en silencio ──
  $$('.inv-react').forEach((btn) => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const { ok, json } = await postJson(URLS.edit, {
          product_id: Number(btn.dataset.productId),
          is_active: true,
        });
        if (!ok || !json.success) {
          showToast((json && json.error) || 'No se pudo reactivar');
          return;
        }
        showToast(`${btn.dataset.name || 'Producto'} reactivado`);
        setTimeout(() => window.location.reload(), 900);
      } finally {
        btn.disabled = false;
      }
    });
  });

  // ── Wire-up ───────────────────────────────────────────────

  function wireUp() {
    const search = $('#inv-search');
    if (search) search.addEventListener('input', applyFilters);

    $$('.cat-pill').forEach((pill) => {
      pill.addEventListener('click', () => {
        $$('.cat-pill').forEach((x) => x.classList.remove('active'));
        pill.classList.add('active');
        applyFilters();
      });
    });

    $$('.inv-price').forEach((cell) => {
      cell.addEventListener('click', () => editPrice(cell));
      cell.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') editPrice(cell);
      });
    });

    const newBtn = $('#inv-new-btn');
    if (newBtn) newBtn.addEventListener('click', openCreate);
    const createCancel = $('#inv-c-cancel');
    if (createCancel) createCancel.addEventListener('click', closeFormPanel);
    const createSave = $('#inv-c-save');
    if (createSave) createSave.addEventListener('click', saveForm);
    $$('.inv-edit').forEach((btn) => {
      btn.addEventListener('click', () => openEdit(btn));
    });
    const createCat = $('#inv-c-cat');
    if (createCat) {
      createCat.addEventListener('change', () => {
        $('#inv-c-catnew-wrap').hidden = createCat.value !== '__new';
      });
    }

    // ── Mínimo desde la recomendación (Fase 3, sin roles) ──────
    $$('.reco-save').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const li = btn.closest('li');
        const input = li.querySelector('input');
        btn.disabled = true;
        try {
          const { ok, json } = await postJson(URLS.minimum, {
            product_id: Number(li.dataset.productId),
            min_stock: (input.value || '').trim() || null,
          });
          if (!ok || !json.success) {
            showToast((json && json.error) || 'No se pudo guardar el mínimo');
            return;
          }
          input.value = json.data.min_stock === null ? '' : json.data.min_stock;
          showToast('Mínimo actualizado');
        } finally {
          btn.disabled = false;
        }
      });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeFormPanel(); closeMov(); closeDel(); closeCats();
      }
    });

    // ── Categorías: renombrar + eliminar (solo vacías) ─────
    function openCats() {
      $('#inv-cats-modal').classList.add('show');
    }

    function closeCats() {
      $('#inv-cats-modal').classList.remove('show');
    }

    function renameCat(li, btn) {
      const span = li.querySelector('.cat-name');
      if (li.querySelector('input.cat-rename-input')) return;
      const input = document.createElement('input');
      input.className = 'cat-rename-input';
      input.value = span.textContent;
      input.setAttribute('aria-label', 'Nuevo nombre');
      span.replaceWith(input);
      input.focus();
      input.select();
      btn.textContent = 'Guardar';
      let done = false;
      const commit = async (save) => {
        if (done) return;
        done = true;
        const value = input.value.trim();
        btn.textContent = 'Renombrar';
        if (!save || !value) {
          window.location.reload();
          return;
        }
        const { ok, json } = await postJson(URLS.catRename, {
          category_id: Number(li.dataset.catId),
          name: value,
        });
        if (!ok || !json.success) {
          showToast((json && json.error) || 'No se pudo renombrar');
          window.location.reload();
          return;
        }
        window.location.reload();
      };
      btn.onclick = () => commit(true);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') commit(true);
        if (e.key === 'Escape') commit(false);
      });
      input.addEventListener('blur', () => commit(true));
    }

    async function deleteCat(li, btn) {
      // Doble clic para confirmar (sin otro modal): arma y ejecuta.
      if (!btn.dataset.armed) {
        btn.dataset.armed = '1';
        btn.textContent = '¿Seguro?';
        setTimeout(() => {
          delete btn.dataset.armed;
          btn.textContent = 'Eliminar';
        }, 3000);
        return;
      }
      const { ok, json } = await postJson(URLS.catDelete, {
        category_id: Number(li.dataset.catId),
      });
      if (!ok || !json.success) {
        // Con productos: en vez del muro, ofrecer destino (P4).
        const msg = (json && json.error) || '';
        if (!ok && /producto\(s\)/i.test(msg)) {
          offerMoveTarget(li);
        } else {
          showToast(msg || 'No se pudo eliminar');
        }
        return;
      }
      window.location.reload();
    }

    // P4: "¿A qué categoría los muevo?" — select inline + confirmar.
    function offerMoveTarget(li) {
      if (li.querySelector('.cat-move-row')) return;
      const others = [];
      $$('#inv-cats-list li[data-cat-id]').forEach((other) => {
        if (other === li) return;
        const nameEl = other.querySelector('.cat-name');
        others.push({
          id: other.dataset.catId,
          name: nameEl ? nameEl.textContent : ('#' + other.dataset.catId),
        });
      });
      if (!others.length) {
        showToast('Es la única categoría: crea otra antes de eliminarla');
        return;
      }
      const row = document.createElement('div');
      row.className = 'cat-move-row';
      const sel = document.createElement('select');
      sel.setAttribute('aria-label', 'Mover productos a');
      others.forEach((o) => {
        const opt = document.createElement('option');
        opt.value = o.id;
        opt.textContent = o.name;
        sel.appendChild(opt);
      });
      const go = document.createElement('button');
      go.type = 'button';
      go.className = 'btn btn-primary';
      go.textContent = 'Mover y eliminar';
      go.addEventListener('click', async () => {
        go.disabled = true;
        try {
          const res = await postJson(URLS.catDelete, {
            category_id: Number(li.dataset.catId),
            move_to_category_id: Number(sel.value),
          });
          if (!res.ok || !res.json.success) {
            showToast((res.json && res.json.error) || 'No se pudo mover');
            return;
          }
          showToast(`Movidos ${res.json.data.moved}: categoría eliminada`);
          setTimeout(() => window.location.reload(), 900);
        } finally {
          go.disabled = false;
        }
      });
      row.appendChild(sel);
      row.appendChild(go);
      li.appendChild(row);
    }

    const catsBtn = $('#inv-cats-btn');
    if (catsBtn) catsBtn.addEventListener('click', openCats);
    const catsClose = $('#inv-cats-close');
    if (catsClose) catsClose.addEventListener('click', closeCats);
    const catsModal = $('#inv-cats-modal');
    if (catsModal) {
      catsModal.addEventListener('click', (e) => {
        if (e.target === catsModal) closeCats();
      });
    }
    $$('#inv-cats-list .cat-rename').forEach((btn) => {
      btn.addEventListener('click', () => {
        renameCat(btn.closest('li'), btn);
      });
    });
    $$('#inv-cats-list .cat-delete').forEach((btn) => {
      btn.addEventListener('click', () => deleteCat(btn.closest('li'), btn));
    });

    // ── Eliminar (soft delete: desactiva, historial intacto) ───
    let delId = null;

    function openDel(btn) {
      delId = Number(btn.dataset.productId);
      $('#inv-del-name').textContent = btn.dataset.name || 'este producto';
      $('#inv-del-modal').classList.add('show');
    }

    function closeDel() {
      $('#inv-del-modal').classList.remove('show');
      delId = null;
    }

    async function confirmDel() {
      if (!delId) return;
      const btn = $('#inv-del-confirm');
      btn.disabled = true;
      try {
        const { ok, json } = await postJson(URLS.remove, {
          product_id: delId,
        });
        if (!ok || !json.success) {
          showToast((json && json.error) || 'No se pudo eliminar');
          return;
        }
        closeDel();
        window.location.reload();
      } finally {
        btn.disabled = false;
      }
    }

    $$('.inv-del').forEach((btn) => {
      btn.addEventListener('click', () => openDel(btn));
    });
    const delCancel = $('#inv-del-cancel');
    if (delCancel) delCancel.addEventListener('click', closeDel);
    const delModal = $('#inv-del-modal');
    if (delModal) {
      delModal.addEventListener('click', (e) => {
        if (e.target === delModal) closeDel();
      });
    }
    const delConfirm = $('#inv-del-confirm');
    if (delConfirm) delConfirm.addEventListener('click', confirmDel);

    // ── Movimiento: compra (lote) o merma ───────────────────
    let movType = 'lote';

    function openMov(btn) {
      $('#inv-m-id').value = btn.dataset.productId;
      $('#inv-m-title').textContent =
        'Movimiento · ' + (btn.dataset.name || '');
      const unitEl = $('#inv-m-unit');
      if (unitEl) unitEl.textContent = btn.dataset.unit || '';
      const row = btn.closest('tr');
      const stockEl = $('#inv-m-stock');
      if (stockEl) {
        stockEl.textContent =
          (row && row.dataset.stock ? row.dataset.stock + ' ' : '') +
          (btn.dataset.unit || '');
      }
      $('#inv-m-qty').value = '';
      $('#inv-m-cost').value = '';
      setMovType('lote');
      $('#inv-mov-modal').classList.add('show');
      $('#inv-m-qty').focus();
    }

    function closeMov() {
      $('#inv-mov-modal').classList.remove('show');
    }

    function setMovType(t) {
      movType = t;
      $$('.mov-tab').forEach((x) => {
        x.classList.toggle('active', x.dataset.mov === t);
      });
      $('#inv-m-cost-wrap').hidden = t !== 'lote';
      $('#inv-m-reason-wrap').hidden = t !== 'merma';
      $('#inv-m-motivo-wrap').hidden = t !== 'ajuste';
      $('#inv-m-stock-line').hidden = t !== 'ajuste';
      // OJO: jamás textContent sobre el label completo — destruiría el
      // span #inv-m-unit interno (bug real: TypeError al alternar tabs).
      const qtyLabel = $('#inv-m-qty-label');
      if (qtyLabel) {
        qtyLabel.textContent = t === 'ajuste' ? 'Cantidad contada' : 'Cantidad';
      }
      const unitWrap = $('#inv-m-unit-wrap');
      if (unitWrap) unitWrap.hidden = t === 'ajuste';
    }

    async function saveMov() {
      const btn = $('#inv-m-save');
      btn.disabled = true;
      try {
        const payload = {
          product_id: Number($('#inv-m-id').value),
        };
        let url;
        let okMsg = 'Movimiento guardado';
        if (movType === 'lote') {
          payload.quantity = $('#inv-m-qty').value.trim();
          payload.total_cost = $('#inv-m-cost').value.trim();
          url = URLS.lot;
        } else if (movType === 'merma') {
          payload.quantity = $('#inv-m-qty').value.trim();
          payload.reason = $('#inv-m-reason').value;
          url = URLS.merma;
        } else {
          // Ajuste firmado: el dueño ingresa lo CONTADO; el backend
          // calcula la diferencia contra el sistema.
          payload.counted = $('#inv-m-qty').value.trim();
          payload.motivo = $('#inv-m-motivo').value;
          url = URLS.ajuste;
          okMsg = 'Ajuste registrado y firmado';
        }
        const { ok, json } = await postJson(url, payload);
        if (!ok || !json.success) {
          showToast((json && json.error) || 'No se pudo guardar');
          return;
        }
        if (movType === 'ajuste' && json.data) {
          const d = Number(json.data.delta);
          showToast(`Ajuste firmado: ${d > 0 ? '+' : ''}${json.data.delta}`);
          setTimeout(() => window.location.reload(), 900);
          return;
        }
        closeMov();
        window.location.reload();
      } finally {
        btn.disabled = false;
      }
    }

    $$('.inv-mov').forEach((btn) => {
      btn.addEventListener('click', () => openMov(btn));
    });
    $$('.mov-tab').forEach((tab) => {
      tab.addEventListener('click', () => setMovType(tab.dataset.mov));
    });
    const movCancel = $('#inv-m-cancel');
    if (movCancel) movCancel.addEventListener('click', closeMov);
    const movModal = $('#inv-mov-modal');
    if (movModal) {
      movModal.addEventListener('click', (e) => {
        if (e.target === movModal) closeMov();
      });
    }
    const movSave = $('#inv-m-save');
    if (movSave) movSave.addEventListener('click', saveMov);

    applyFilters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();

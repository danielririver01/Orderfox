/*
 * Ventas del Día — vanilla JS (convención del repo: JS separado).
 * Todo es lectura real del día Bogotá servida por la ruta: filtros,
 * paginación cliente, CSV (construido del mismo JSON), modal de ticket
 * e impresión. Sin cierre Z en v1 (sin backend de caja).
 */
(function () {
  'use strict';

  // Datos desde el bloque JSON (patrón pos.html: nunca JS inline).
  let SALES = [];
  try {
    SALES = JSON.parse(
      (document.getElementById('ventas-data') || {}).textContent || '[]');
  } catch (err) {
    SALES = [];
  }
  const CSRF_TOKEN = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  const PAGE_SIZE = 12;
  let page = 0;

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  function showToast(msg) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  // ── Filtros: texto + método ───────────────────────────────

  function currentMethod() {
    const active = $('.cat-pill.active');
    return active ? String(active.dataset.method || '') : '';
  }

  function visibleRows() {
    const text = (($('#vtas-search') || {}).value || '').trim().toLowerCase();
    const method = currentMethod();
    return Array.from($$('.vtas-row')).filter((row) => {
      const okText = !text || (row.dataset.search || '').includes(text);
      const okMethod = !method || String(row.dataset.method || '') === method;
      return okText && okMethod;
    });
  }

  function applyFilters(resetPage) {
    if (resetPage) page = 0;
    const rows = visibleRows();
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (page >= pages) page = pages - 1;
    $$('.vtas-row').forEach((row) => { row.style.display = 'none'; });
    rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)
      .forEach((row) => { row.style.display = ''; });
    const pager = $('#vtas-pager');
    if (pager) pager.hidden = rows.length <= PAGE_SIZE;
    const label = $('#vtas-page-label');
    if (label) label.textContent = `Pág. ${page + 1} de ${pages}`;
    const empty = $('#vtas-noresults');
    if (empty) empty.hidden = !(rows.length === 0 && SALES.length > 0);
    const count = $('#vtas-count');
    if (count) count.textContent = rows.length;
  }

  // ── Modal de ticket (ver + reimprimir) ────────────────────

  function findSale(number) {
    return SALES.find((s) => String(s.number) === String(number));
  }

  function openTicket(number) {
    const s = findSale(number);
    if (!s) {
      showToast('Ticket no encontrado');
      return;
    }
    $('#vtas-m-num').textContent = '#' + s.number;
    $('#vtas-m-customer').textContent = 'Cliente: ' + (s.customer || 'Cliente General');
    $('#vtas-m-method').textContent = 'Método: ' + (s.method || 'Sin registro');
    const body = $('#vtas-m-items');
    body.innerHTML = '';
    (s.items || []).forEach((it) => {
      const tr = document.createElement('tr');
      const tdName = document.createElement('td');
      tdName.textContent = `${it.name} — ${it.qty} ${it.unit}`;
      const tdTotal = document.createElement('td');
      tdTotal.textContent = '$' + it.total;
      tr.appendChild(tdName);
      tr.appendChild(tdTotal);
      body.appendChild(tr);
    });
    $('#vtas-m-total').textContent = '$' + s.total;
    $('#vtas-modal').classList.add('show');
    document.body.classList.add('print-ticket');
  }

  function closeTicket() {
    $('#vtas-modal').classList.remove('show');
    document.body.classList.remove('print-ticket');
  }

  // ── CSV real (del mismo JSON servido, sin inventar) ───────

  function downloadCsv() {
    if (!SALES.length) {
      showToast('No hay ventas hoy para exportar');
      return;
    }
    const rows = [['ticket', 'hora', 'cliente', 'metodo', 'total',
      'items']];
    SALES.forEach((s) => {
      rows.push([
        s.number, s.time, s.customer || '', s.method || '',
        s.total,
        (s.items || []).map((it) => `${it.name} ${it.qty}${it.unit}`)
          .join(' | '),
      ]);
    });
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'ventas-hoy.csv';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  // ── Wire-up ───────────────────────────────────────────────

  function wireUp() {
    const search = $('#vtas-search');
    if (search) search.addEventListener('input', () => applyFilters(true));

    $$('.cat-pill').forEach((pill) => {
      pill.addEventListener('click', () => {
        $$('.cat-pill').forEach((x) => x.classList.remove('active'));
        pill.classList.add('active');
        applyFilters(true);
      });
    });

    const prev = $('#vtas-prev');
    if (prev) prev.addEventListener('click', () => {
      if (page > 0) { page -= 1; applyFilters(false); }
    });
    const next = $('#vtas-next');
    if (next) next.addEventListener('click', () => {
      page += 1; applyFilters(false);
    });

    $$('.vtas-view').forEach((btn) => {
      btn.addEventListener('click', () => openTicket(btn.dataset.number));
    });

    const close = $('#vtas-m-close');
    if (close) close.addEventListener('click', closeTicket);
    const modal = $('#vtas-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeTicket();
      });
    }
    const printBtn = $('#vtas-m-print');
    if (printBtn) printBtn.addEventListener('click', () => window.print());

    const toolbarPrint = $('#vtas-print');
    if (toolbarPrint) {
      toolbarPrint.addEventListener('click', () => {
        // Sin ventas no hay nada que imprimir: mensaje, no hoja en blanco.
        if (!SALES.length) {
          showToast('No hay ventas hoy para imprimir');
          return;
        }
        window.print();
      });
    }

    const csvBtn = $('#vtas-csv');
    if (csvBtn) csvBtn.addEventListener('click', downloadCsv);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeTicket(); closeCierre(); }
    });

    // ── Cierre Final Z (firma con conteo; duplicado lo frena el backend) ──
    const CIERRE = window.VENTAS_CIERRE || null;

    function openCierre() {
      const modal = $('#vtas-cierre-modal');
      if (!modal) return;
      const input = $('#vtas-cierre-counted');
      if (input) input.value = '';
      updateCierreDiff();
      modal.classList.add('show');
      if (input) input.focus();
    }

    function closeCierre() {
      const modal = $('#vtas-cierre-modal');
      if (modal) modal.classList.remove('show');
    }

    function cierreCounted() {
      const input = $('#vtas-cierre-counted');
      if (!input) return null;
      const raw = String(input.value || '').trim().replace(/[.,\s]/g, '');
      if (!raw) return null;
      const v = Number(raw);
      return Number.isFinite(v) && v >= 0 ? v : NaN;
    }

    function updateCierreDiff() {
      const el = $('#vtas-cierre-diff');
      if (!el || !CIERRE) return;
      const counted = cierreCounted();
      if (counted === null || Number.isNaN(counted)) {
        el.textContent = '$0';
        return;
      }
      const diff = Math.round(counted - (CIERRE.expected || 0));
      const abs = Math.abs(diff).toLocaleString('es-CO');
      el.textContent = (diff < 0 ? '-$' : diff > 0 ? '+$' : '$') + abs;
    }

    async function confirmCierre() {
      if (!CIERRE) return;
      const counted = cierreCounted();
      if (counted === null || Number.isNaN(counted)) {
        showToast('Escribe el efectivo contado');
        return;
      }
      const btn = $('#vtas-cierre-confirm');
      btn.disabled = true;
      try {
        const res = await fetch(CIERRE.closeUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': CSRF_TOKEN,
          },
          body: JSON.stringify({ counted_cash: counted, day: CIERRE.day }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok || !json.success) {
          showToast((json && json.error) || 'No se pudo firmar el cierre');
          return;
        }
        showToast('Caja cerrada por hoy');
        setTimeout(() => window.location.reload(), 900);
      } catch (err) {
        showToast('Sin conexión con el servidor');
      } finally {
        btn.disabled = false;
      }
    }

    const cierreOpen = $('#vtas-cierre-open');
    if (cierreOpen) cierreOpen.addEventListener('click', openCierre);
    const cierreCancel = $('#vtas-cierre-cancel');
    if (cierreCancel) cierreCancel.addEventListener('click', closeCierre);
    const cierreModal = $('#vtas-cierre-modal');
    if (cierreModal) {
      cierreModal.addEventListener('click', (e) => {
        if (e.target === cierreModal) closeCierre();
      });
    }
    const cierreInput = $('#vtas-cierre-counted');
    if (cierreInput) cierreInput.addEventListener('input', updateCierreDiff);
    const cierreConfirm = $('#vtas-cierre-confirm');
    if (cierreConfirm) cierreConfirm.addEventListener('click', confirmCierre);

    // ── Libro de caja mínimo (ingreso/retiro del día) ──────
    let movType = 'ingreso';

    function openMov() {
      const amount = $('#vtas-mov-amount');
      if (amount) amount.value = '';
      const reason = $('#vtas-mov-reason');
      if (reason) reason.value = '';
      setMovType('ingreso');
      $('#vtas-mov-modal').classList.add('show');
      if (amount) amount.focus();
    }

    function closeMov() {
      $('#vtas-mov-modal').classList.remove('show');
      resetMovConfirm();
    }

    function resetMovConfirm() {
      const btn = $('#vtas-mov-confirm');
      if (btn) {
        delete btn.dataset.armed;
        btn.textContent = 'Guardar';
      }
    }

    function setMovType(t) {
      movType = t;
      $$('#vtas-mov-modal .mov-tab').forEach((x) => {
        x.classList.toggle('active', x.dataset.mov === t);
      });
      resetMovConfirm();
    }

    function movAmount() {
      const amountEl = $('#vtas-mov-amount');
      const raw = String((amountEl && amountEl.value) || '').trim()
        .replace(/[.,\s]/g, '');
      if (!raw) return null;
      const v = Number(raw);
      return Number.isFinite(v) && v > 0 ? { raw, v } : NaN;
    }

    function movPreview() {
      // Doble confirmación con monto formateado: evita dedos gordos de
      // cientos de millones (caso real: retiro de $250M por error).
      const btn = $('#vtas-mov-confirm');
      const parsed = movAmount();
      if (parsed === null || Number.isNaN(parsed)) {
        showToast('Escribe el monto');
        return null;
      }
      if (!btn.dataset.armed) {
        btn.dataset.armed = '1';
        const label = movType === 'ingreso' ? 'un INGRESO' : 'un RETIRO';
        btn.textContent = `¿${label} de $${parsed.v.toLocaleString('es-CO')}? Toca de nuevo`;
        setTimeout(() => {
          delete btn.dataset.armed;
          btn.textContent = 'Guardar';
        }, 4000);
        return null;
      }
      delete btn.dataset.armed;
      btn.textContent = 'Guardar';
      return parsed;
    }

    async function confirmMov() {
      if (!CIERRE || !CIERRE.movUrl) return;
      const parsed = movPreview();
      if (!parsed) return;
      const btn = $('#vtas-mov-confirm');
      btn.disabled = true;
      try {
        const res = await fetch(CIERRE.movUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': CSRF_TOKEN,
          },
          body: JSON.stringify({
            tipo: movType,
            monto: parsed.raw,
            motivo: ($('#vtas-mov-reason') || {}).value || '',
          }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok || !json.success) {
          showToast((json && json.error) || 'No se pudo guardar');
          return;
        }
        showToast(movType === 'ingreso' ? 'Ingreso registrado' : 'Retiro registrado');
        setTimeout(() => window.location.reload(), 900);
      } catch (err) {
        showToast('Sin conexión con el servidor');
      } finally {
        btn.disabled = false;
      }
    }

    const movOpen = $('#vtas-mov-open');
    if (movOpen) movOpen.addEventListener('click', openMov);
    const movCancel = $('#vtas-mov-cancel');
    if (movCancel) movCancel.addEventListener('click', closeMov);
    const movModal = $('#vtas-mov-modal');
    if (movModal) {
      movModal.addEventListener('click', (e) => {
        if (e.target === movModal) closeMov();
      });
    }
    $$('#vtas-mov-modal .mov-tab').forEach((tab) => {
      tab.addEventListener('click', () => setMovType(tab.dataset.mov));
    });
    const movConfirm = $('#vtas-mov-confirm');
    if (movConfirm) movConfirm.addEventListener('click', confirmMov);

    // ── Día consultado: Hoy / Ayer / fecha (el backend valida y clampa) ──
    const dayInput = $('#vtas-day');
    if (dayInput && CIERRE && CIERRE.baseUrl) {
      dayInput.addEventListener('change', () => {
        if (dayInput.value) {
          window.location.href = `${CIERRE.baseUrl}?day=${dayInput.value}`;
        }
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeMov();
    });

    applyFilters(true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();

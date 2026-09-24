/*
 * Clientes / Fiados — vanilla JS (convención del repo: JS separado).
 * La deuda NUNCA se edita: solo abonos y fecha de compromiso. Todo por
 * sesión del POS (cookie), sin roles en v1.
 */
(function () {
  'use strict';

  const CSRF_TOKEN = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  const BASE = (window.CTES_URLS || {}).base || '';

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

  // ── Buscador ──────────────────────────────────────────────

  function applyFilters() {
    const text = (($('#ctes-search') || {}).value || '').trim().toLowerCase();
    let shown = 0;
    const rows = $$('.ctes-row');
    rows.forEach((row) => {
      const show = !text || (row.dataset.name || '').includes(text);
      row.style.display = show ? '' : 'none';
      if (show) shown += 1;
    });
    const empty = $('#ctes-noresults');
    if (empty) empty.hidden = rows.length === 0 || shown !== 0;
  }

  // ── Abono (nunca mayor al saldo: lo frena el backend) ─────

  async function abonar(row, btn) {
    const input = row.querySelector('.ctes-monto');
    const raw = String((input && input.value) || '').trim()
      .replace(/[.,\s]/g, '');
    if (!raw) {
      showToast('Escribe el monto a abonar');
      return;
    }
    btn.disabled = true;
    try {
      const { ok, json } = await postJson(
        `${BASE}/${row.dataset.clientId}/abonar`, { monto: raw });
      if (!ok || !json.success) {
        showToast((json && json.error) || 'No se pudo abonar');
        return;
      }
      showToast(`Abono registrado. Saldo: $${json.data.saldo}`);
      setTimeout(() => window.location.reload(), 900);
    } catch (err) {
      showToast('Sin conexión con el servidor');
    } finally {
      btn.disabled = false;
    }
  }

  // ── Compromiso (fecha o vacío para quitarla) ──────────────

  async function guardarCompromiso(row, input) {
    const { ok, json } = await postJson(
      `${BASE}/${row.dataset.clientId}/compromiso`,
      { fecha_compromiso: input.value || null });
    if (!ok || !json.success) {
      showToast((json && json.error) || 'No se pudo guardar la fecha');
      return;
    }
    showToast(json.data.fecha_compromiso ? 'Compromiso guardado' : 'Compromiso quitado');
  }

  // ── Detalle expandible (tickets + abonos) ─────────────────

  function openDetalle(row) {
    const cid = row.dataset.clientId;
    fetch(`${BASE}/${cid}`)
      .then((res) => res.json())
      .then((json) => {
        if (!json.success) {
          showToast(json.error || 'No se pudo abrir la cuenta');
          return;
        }
        const d = json.data;
        $('#ctes-m-name').textContent = d.client.name;
        $('#ctes-m-saldo').textContent = `Deuda actual: $${d.saldo}`;
        const tBody = $('#ctes-m-tickets');
        tBody.innerHTML = '';
        (d.tickets || []).forEach((t) => {
          const tr = document.createElement('tr');
          const a = document.createElement('td');
          a.textContent = t.number;
          const b = document.createElement('td');
          b.textContent = '$' + t.total;
          tr.appendChild(a);
          tr.appendChild(b);
          tBody.appendChild(tr);
        });
        if (!d.tickets.length) {
          const tr = document.createElement('tr');
          const td = document.createElement('td');
          td.textContent = 'Sin tickets fiados.';
          tr.appendChild(td);
          tBody.appendChild(tr);
        }
        const aBody = $('#ctes-m-abonos');
        aBody.innerHTML = '';
        (d.abonos || []).forEach((a) => {
          const tr = document.createElement('tr');
          const tdA = document.createElement('td');
          tdA.textContent = '$' + a.monto;
          const tdB = document.createElement('td');
          tdB.textContent = (a.registered_at || '').slice(0, 10);
          tr.appendChild(tdA);
          tr.appendChild(tdB);
          aBody.appendChild(tr);
        });
        if (!d.abonos.length) {
          const tr = document.createElement('tr');
          const td = document.createElement('td');
          td.textContent = 'Sin abonos aún.';
          tr.appendChild(td);
          aBody.appendChild(tr);
        }
        $('#ctes-modal').classList.add('show');
      })
      .catch(() => showToast('Sin conexión con el servidor'));
  }

  function closeDetalle() {
    $('#ctes-modal').classList.remove('show');
  }

  // ── Wire-up ───────────────────────────────────────────────

  function wireUp() {
    const search = $('#ctes-search');
    if (search) search.addEventListener('input', applyFilters);

    $$('.ctes-abonar').forEach((btn) => {
      btn.addEventListener('click', () => abonar(btn.closest('tr'), btn));
    });
    $$('.ctes-fecha').forEach((input) => {
      input.addEventListener('change', () => {
        guardarCompromiso(input.closest('tr'), input);
      });
    });
    $$('.ctes-ver').forEach((btn) => {
      btn.addEventListener('click', () => openDetalle(btn.closest('tr')));
    });

    const close = $('#ctes-m-close');
    if (close) close.addEventListener('click', closeDetalle);
    const modal = $('#ctes-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeDetalle();
      });
    }
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDetalle();
    });

    applyFilters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();

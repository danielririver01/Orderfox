/*
 * Clientes / Fiados v2 — vanilla JS (convención del repo: JS separado).
 * Panel del diseño Stitch portado: búsqueda, chips de estado, ficha
 * modal (saldo/cupo/timeline/abono rápido) y nueva libreta.
 * El backend manda dinero ya formateado es-CO; aquí solo se muestra.
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
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    return { ok: res.ok, json };
  }

  // ── Iniciales para el avatar circular (diseño Stitch) ────────

  function initials(name) {
    return String(name || '').trim().split(/\s+/)
      .slice(0, 2).map((w) => w[0] || '').join('').toUpperCase() || '?';
  }

  function paintInitials(scope) {
    (scope || document).querySelectorAll('.ctes-initials').forEach((el) => {
      el.textContent = initials(el.dataset.name);
    });
  }

  // ── Reloj Bogotá del topbar ──────────────────────────────────

  function startClock() {
    const el = $('#ctes-clock');
    if (!el) return;
    const tz = el.dataset.tz || 'America/Bogota';
    const tick = () => {
      el.textContent = new Intl.DateTimeFormat('es-CO', {
        hour: '2-digit', minute: '2-digit', timeZone: tz, hour12: true,
      }).format(new Date());
    };
    tick();
    setInterval(tick, 30000);
  }

  // ── Búsqueda + chips de estado ───────────────────────────────

  let currentFilter = 'todos';

  function rowMatches(row) {
    const text = (($('#ctes-search') || {}).value || '').trim().toLowerCase();
    const okText = !text || (row.dataset.name || '').toLowerCase().includes(text)
      || (row.dataset.phone || '').includes(text);
    const estado = row.dataset.estado;
    const okFilter = currentFilter === 'todos'
      || (currentFilter === 'saldo' && estado !== 'pagada')
      || currentFilter === estado;
    return okText && okFilter;
  }

  function applyFilters() {
    let shown = 0;
    $$('.ctes-row').forEach((row) => {
      const show = rowMatches(row);
      row.style.display = show ? '' : 'none';
      if (show) shown += 1;
    });
    const visible = $('[data-count-visible]');
    if (visible) visible.textContent = shown;
    const empty = $('#ctes-noresults');
    if (empty) empty.hidden = shown !== 0;
    const emptyM = $('#ctes-noresults-mobile');
    if (emptyM) emptyM.hidden = shown !== 0;
  }

  function paintCounts() {
    const counts = { todos: 0, saldo: 0, vencida: 0, al_dia: 0 };
    $$('.ctes-row').forEach((row) => {
      counts.todos += 1;
      if (row.dataset.estado !== 'pagada') counts.saldo += 1;
      if (row.dataset.estado === 'vencida') counts.vencida += 1;
      if (row.dataset.estado === 'al_dia') counts.al_dia += 1;
    });
    $$('[data-count]').forEach((el) => {
      el.textContent = counts[el.dataset.count] || 0;
    });
  }

  function wireChips() {
    $$('.ctes-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        currentFilter = chip.dataset.filter || 'todos';
        $$('.ctes-chip').forEach((c) => {
          c.classList.remove('bg-secondary-container', 'text-on-secondary-container', 'font-bold');
          c.classList.add('bg-surface-low', 'text-secondary', 'font-semibold');
        });
        chip.classList.add('bg-secondary-container', 'text-on-secondary-container', 'font-bold');
        chip.classList.remove('bg-surface-low', 'text-secondary', 'font-semibold');
        applyFilters();
      });
    });
  }

  // ── Abono: presets dinámicos del saldo (25/50/75/Total) ─────

  function fmtCop(value) {
    return '$' + Number(value).toLocaleString('es-CO', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function presetRaw(pct, saldoRaw) {
    // Redondeo a peso (los centavos de la libreta no se abonan a mano).
    // Total = saldo exacto tal cual (la deuda real, sin redondeos).
    if (pct === 'total') return saldoRaw;
    return Math.round(saldoRaw * (Number(pct) / 100));
  }

  function renderPresets(saldoRaw) {
    $$('#ctes-ab-presets .ctes-preset').forEach((btn) => {
      const raw = presetRaw(btn.dataset.pct, saldoRaw);
      const amt = btn.querySelector('.ctes-preset-amt');
      if (amt) amt.textContent = fmtCop(raw);
      // Sin deuda (o presets a $0) el botón se apaga: no hay nada que abonar.
      btn.disabled = raw <= 0;
      btn.dataset.raw = String(raw);
    });
  }

  // ── Ficha modal ──────────────────────────────────────────────

  const modal = () => $('#ctes-modal');

  function openFicha(id, focusAbono) {
    const shell = modal();
    if (!shell) return;
    fetch(`${BASE}/${id}`)
      .then((res) => res.json())
      .then((json) => {
        if (!json.success) {
          showToast(json.error || 'No se pudo abrir la cuenta');
          return;
        }
        fillFicha(json.data, id);
        shell.classList.add('open');
        document.body.classList.add('modal-open');
        if (focusAbono) {
          const input = $('#ctes-ab-monto');
          if (input) input.focus();
        }
      })
      .catch(() => showToast('Sin conexión con el servidor'));
  }

  function closeFicha() {
    const shell = modal();
    if (shell) shell.classList.remove('open');
    document.body.classList.remove('modal-open');
  }

  let currentClient = { id: null, saldoRaw: 0 };

  function fillFicha(d, id) {
    const client = d.client || {};
    currentClient = {
      id,
      saldoRaw: parseFloat(d.saldo_raw || '0') || 0,
    };
    $('#ctes-m-name').textContent = client.name || '—';
    $('#ctes-m-phone').textContent = client.phone || '';
    $('#ctes-m-saldo').textContent = d.saldo;
    $('#ctes-m-cupo').textContent = d.credit_limit || 'Sin límite';
    $('#ctes-m-disponible').textContent = d.disponible || '—';
    $('#ctes-m-uso').textContent = d.uso_pct != null ? `${d.uso_pct}% del cupo` : '';
    const gaugeWrap = $('#ctes-m-gauge-wrap');
    const gauge = $('#ctes-m-gauge');
    if (gaugeWrap && gauge) {
      gaugeWrap.hidden = d.uso_pct == null;
      gauge.style.width = `${d.uso_pct || 0}%`;
    }
    const fecha = $('#ctes-m-fecha');
    if (fecha) fecha.value = client.fecha_compromiso || '';
    const noteText = $('#ctes-m-note-text');
    const noteInput = $('#ctes-m-note-input');
    const noteSave = $('#ctes-m-note-save');
    if (noteText) noteText.textContent = d.internal_note
      || 'Sin nota aún. Guardá el contexto del vecino (cuándo paga, cómo tratarlo).';
    if (noteInput) { noteInput.value = d.internal_note || ''; noteInput.classList.add('hidden'); }
    if (noteSave) noteSave.classList.add('hidden');
    paintInitials($('.ficha-inner') ? $('#ctes-modal') : document);

    const monto = $('#ctes-ab-monto');
    if (monto) monto.value = '';
    // Presets dinámicos: etiquetas y valores derivados del saldo crudo.
    renderPresets(currentClient.saldoRaw);

    // Timeline unificado (+ cargo / − abono), como la libreta de papel.
    const timeline = $('#ctes-m-timeline');
    timeline.innerHTML = '';
    const items = d.timeline || [];
    $('#ctes-m-count').textContent = items.length
      ? `${items.length} movimiento(s)` : '';
    if (!items.length) {
      timeline.innerHTML = '<p class="text-body-sm text-secondary">Sin movimientos aún.</p>';
    }
    items.forEach((m) => {
      const rowEl = document.createElement('div');
      const isAbono = m.kind === 'abono';
      rowEl.className = `p-space-sm rounded-xl flex items-start justify-between gap-space-sm ${
        isAbono ? 'bg-secondary-container/30' : 'bg-surface-low'}`;
      const left = document.createElement('div');
      left.className = 'flex items-start gap-space-xs min-w-0';
      const icon = document.createElement('span');
      icon.className = 'material-symbols-outlined text-[18px] shrink-0 mt-0.5';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = isAbono ? 'check' : 'shopping_basket';
      const texts = document.createElement('div');
      texts.className = 'flex flex-col min-w-0';
      const title = document.createElement('span');
      title.className = 'text-label-lg font-bold text-on-surface';
      title.textContent = isAbono
        ? `Abono${m.method ? ' · ' + m.method : ''}`
        : `Compra a fiado #${m.number}`;
      const sub = document.createElement('span');
      sub.className = 'text-body-sm text-secondary truncate';
      sub.textContent = isAbono
        ? (m.at || '').slice(0, 16).replace('T', ' ')
        : (m.description || '');
      texts.appendChild(title);
      texts.appendChild(sub);
      left.appendChild(icon);
      left.appendChild(texts);
      const amount = document.createElement('span');
      amount.className = `text-title-md font-extrabold shrink-0 ${
        isAbono ? 'text-primary' : 'text-tertiary-container'}`;
      amount.textContent = isAbono ? `- ${m.amount}` : `+ ${m.amount}`;
      rowEl.appendChild(left);
      rowEl.appendChild(amount);
      timeline.appendChild(rowEl);
    });
  }

  // ── Abono rápido (presets + método + submit) ─────────────────

  function wireAbono() {
    $$('.ctes-preset').forEach((btn) => {
      btn.addEventListener('click', () => {
        const monto = $('#ctes-ab-monto');
        if (!monto) return;
        // Valor crudo calculado al abrir la ficha (nunca re-parsea "$1.234").
        monto.value = btn.dataset.raw || '0';
      });
    });
    const submit = $('#ctes-ab-submit');
    if (submit) {
      submit.addEventListener('click', async () => {
        if (!currentClient.id) return;
        const monto = $('#ctes-ab-monto');
        const raw = String((monto && monto.value) || '').trim();
        if (!raw || Number(raw) <= 0) {
          showToast('Escribe el monto a abonar');
          return;
        }
        const method = (document.querySelector('input[name="ctes-ab-method"]:checked') || {}).value || 'efectivo';
        submit.disabled = true;
        try {
          const { ok, json } = await postJson(
            `${BASE}/${currentClient.id}/abonar`, { monto: raw, method });
          if (!ok || !json.success) {
            showToast((json && json.error) || 'No se pudo abonar');
            return;
          }
          showToast(`Abono registrado. Saldo: ${json.data.saldo}`);
          setTimeout(() => window.location.reload(), 900);
        } catch (err) {
          showToast('Sin conexión con el servidor');
        } finally {
          submit.disabled = false;
        }
      });
    }
  }

  // ── Compromiso y nota (desde la ficha) ───────────────────────

  function wireFichaEdits() {
    const fecha = $('#ctes-m-fecha');
    if (fecha) {
      fecha.addEventListener('change', async () => {
        if (!currentClient.id) return;
        const { ok, json } = await postJson(
          `${BASE}/${currentClient.id}/compromiso`,
          { fecha_compromiso: fecha.value || null });
        showToast(ok && json.success
          ? (fecha.value ? 'Compromiso guardado' : 'Compromiso quitado')
          : ((json && json.error) || 'No se pudo guardar'));
      });
    }
    const noteEdit = $('#ctes-m-note-edit');
    const noteInput = $('#ctes-m-note-input');
    const noteSave = $('#ctes-m-note-save');
    if (noteEdit && noteInput && noteSave) {
      noteEdit.addEventListener('click', () => {
        noteInput.classList.toggle('hidden');
        noteSave.classList.toggle('hidden');
        if (!noteInput.classList.contains('hidden')) noteInput.focus();
      });
      noteSave.addEventListener('click', async () => {
        const { ok, json } = await postJson(
          `${BASE}/${currentClient.id}/ficha`,
          { internal_note: noteInput.value });
        if (!ok || !json.success) {
          showToast((json && json.error) || 'No se pudo guardar la nota');
          return;
        }
        $('#ctes-m-note-text').textContent = json.data.internal_note
          || 'Sin nota aún.';
        noteInput.classList.add('hidden');
        noteSave.classList.add('hidden');
        showToast('Nota guardada');
      });
    }
  }

  // ── Nueva libreta ────────────────────────────────────────────

  function wireNueva() {
    const openBtn = $('#ctes-new-open');
    const shell = $('#ctes-new-modal');
    const open = () => {
      if (shell) { shell.classList.add('open'); document.body.classList.add('modal-open'); }
      const input = $('#ctes-new-name');
      if (input) input.focus();
    };
    const close = () => {
      if (shell) shell.classList.remove('open');
      document.body.classList.remove('modal-open');
    };
    if (openBtn) openBtn.addEventListener('click', open);
    const closeBtn = $('#ctes-new-close');
    if (closeBtn) closeBtn.addEventListener('click', close);
    const save = $('#ctes-new-save');
    if (save) {
      save.addEventListener('click', async () => {
        const name = ($('#ctes-new-name') || {}).value || '';
        const phone = ($('#ctes-new-phone') || {}).value || '';
        if (!name.trim()) { showToast('Escribe el nombre del vecino'); return; }
        save.disabled = true;
        try {
          const { ok, json } = await postJson(BASE, { name, phone });
          if (!ok || !json.success) {
            showToast((json && json.error) || 'No se pudo crear');
            return;
          }
          showToast(json.data.created ? 'Libreta creada' : 'Ya existía, abierta');
          setTimeout(() => window.location.reload(), 900);
        } catch (err) {
          showToast('Sin conexión con el servidor');
        } finally {
          save.disabled = false;
        }
      });
    }
  }

  // ── Wire-up ──────────────────────────────────────────────────

  function wireUp() {
    paintInitials(document);
    paintCounts();
    startClock();

    const search = $('#ctes-search');
    if (search) search.addEventListener('input', applyFilters);
    wireChips();

    $$('.ctes-row').forEach((row) => {
      row.addEventListener('click', (e) => {
        if (e.target.closest('button, a, input, label')) return;
        openFicha(row.dataset.id, false);
      });
    });
    $$('.ctes-ver').forEach((btn) => {
      btn.addEventListener('click', () => {
        const row = btn.closest('.ctes-row');
        if (row) openFicha(row.dataset.id, false);
      });
    });
    $$('.ctes-abonar').forEach((btn) => {
      btn.addEventListener('click', () => {
        const row = btn.closest('.ctes-row');
        if (row) openFicha(row.dataset.id, true);
      });
    });
    const quick = $('#ctes-focus-search');
    if (quick) {
      quick.addEventListener('click', () => {
        const searchInput = $('#ctes-search');
        if (searchInput) searchInput.focus();
      });
    }

    const shell = modal();
    if (shell) {
      shell.addEventListener('click', (e) => {
        if (e.target === shell) closeFicha();
      });
    }
    const mClose = $('#ctes-m-close');
    if (mClose) mClose.addEventListener('click', closeFicha);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeFicha();
    });

    wireAbono();
    wireFichaEdits();
    wireNueva();
    applyFilters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();

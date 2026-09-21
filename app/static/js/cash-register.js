/**
 * cash-register.js — Centro de Caja (/cash-register)
 *
 * Carga resumen + desglose por método + pedidos pagados + pendientes + cierres
 * vía fetch. El "Registrar pago" de pendientes reutiliza payment-modal.js en
 * mode='register' (POST /orders/<id>/payment); al confirmar, recarga la página
 * para refrescar todo.
 */

let crState = {
    range: 'today',
    customFrom: '',
    customTo: '',
    method: null,   // filtro activo por método de pago
    search: '',
    requestInFlight: false,
    summaryAll: null,  // total del periodo sin filtro (para el modal de cierre)
    shift: null,       // turno abierto vigente (o null)
    shiftExpected: 0,
    cashStrict: false, // flag del admin: apertura + conteo obligatorios
    shiftInFlight: false,
    drawerEnabled: false, // cajón físico declarado por el admin
    drawerAuto: false,    // apertura automática al cobrar en efectivo
    drawerInFlight: false,
};

const crEl = (id) => document.getElementById(id);

function crGetCSRF() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function formatCOP(value) {
    return '$' + Number(value || 0).toLocaleString('es-CO');
}

function crUrl(path, params) {
    const url = new URL(path, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
        if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
    });
    return url.toString();
}

function crRangeParams() {
    const p = { range: crState.range };
    if (crState.range === 'custom') {
        p.from = crState.customFrom;
        p.to = crState.customTo;
    }
    return p;
}

/* Rango custom válido = ambas fechas seleccionadas y orden correcto.
   Sin esto, loadSummary/loadOrders dispararían un 400 con range=custom
   vacío al hacer clic en un método, buscar o refrescar. */
function crCustomRangeComplete() {
    if (crState.range !== 'custom') return true;
    return !!(crState.customFrom && crState.customTo && crState.customFrom <= crState.customTo);
}

function crShowCustomRangeError() {
    const err = crEl('custom-range-error');
    if (err) {
        err.textContent = 'Selecciona las fechas y pulsa "Aplicar" para ver este método en el rango personalizado.';
        err.classList.remove('hidden');
    }
}

/* ── Carga de datos ────────────────────────────────────────────────────── */

async function loadSummary() {
    if (!crCustomRangeComplete()) {
        crShowCustomRangeError();
        return;
    }
    try {
        const res = await fetch(crUrl('/cash-register/api/summary', crRangeParams()));
        const body = await res.json();
        if (!res.ok || !body.success) throw new Error(body.error || 'Error al cargar resumen');

        const d = body.data;
        crState.summaryAll = d;  // total del periodo (sin filtro) para el modal de cierre

        // Tarjetas de resumen: si hay un método activo, muestran SOLO ese método
        let sales = d.total_sales;
        let orders = d.total_orders;
        if (crState.method) {
            const m = d.breakdown[crState.method] || { total: 0, orders: 0 };
            sales = m.total;
            orders = m.orders;
        }
        crEl('stat-sales').textContent = formatCOP(sales);
        crEl('stat-orders').textContent = orders;
        crEl('stat-avg').textContent = formatCOP(orders ? Math.round(sales / orders) : 0);

        // Desglose por método
        document.querySelectorAll('[data-method-total]').forEach((el) => {
            const method = el.closest('[data-method]').dataset.method;
            el.textContent = formatCOP(d.breakdown[method]?.total || 0);
        });
        document.querySelectorAll('[data-method-count]').forEach((el) => {
            const method = el.closest('[data-method]').dataset.method;
            const n = d.breakdown[method]?.orders || 0;
            el.textContent = n + (n === 1 ? ' pedido' : ' pedidos');
        });

        // Resumen del modal de cierre → SIEMPRE el total del periodo completo
        crEl('close-summary-sales').textContent = formatCOP(d.total_sales);
        crEl('close-summary-orders').textContent = d.total_orders;
    } catch (err) {
        console.error('loadSummary:', err);
    }
}

async function loadOrders() {
    if (!crCustomRangeComplete()) {
        crShowCustomRangeError();
        return;
    }
    const list = crEl('orders-list');
    list.innerHTML = '<div class="text-center text-gray-600 text-sm py-8">Cargando pedidos…</div>';
    try {
        const res = await fetch(crUrl('/cash-register/api/orders', {
            ...crRangeParams(),
            method: crState.method || null,
            q: crState.search || null,
        }));
        const body = await res.json();
        if (!res.ok || !body.success) throw new Error(body.error || 'Error al cargar pedidos');

        renderOrders(list, body.data);
    } catch (err) {
        list.innerHTML = '<div class="text-center text-red-400 text-sm py-8">No se pudieron cargar los pedidos</div>';
    }
}

function renderOrders(list, orders) {
    if (!orders.length) {
        list.innerHTML = '<div class="text-center text-gray-600 text-sm py-8">Sin pedidos en este periodo</div>';
        return;
    }
    const actorLine = (actor, prefix) => {
        if (!actor) return '';
        const who = actor.name
            ? `${escapeHtml(actor.name)} (${escapeHtml(actor.role_label)})`
            : `(${escapeHtml(actor.role_label)})`;
        const when = actor.time ? ` · ${localTime(actor.time)}` : '';
        return `<p class="text-[9px] text-gray-600 font-bold mt-0.5">${prefix}: ${who}${when}</p>`;
    };
    list.innerHTML = orders.map((o) => `
        <a href="/orders/${o.id}" class="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-[#141414] border border-[#262626] hover:border-[#f2460d]/40 transition-all">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                    <span class="text-sm font-black text-white tracking-tight">${o.order_number}</span>
                    <span class="px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border ${methodBadgeClasses(o.payment_method)}">${methodLabel(o.payment_method)}</span>
                </div>
                ${o.customer_name ? `<p class="text-[11px] text-gray-500 font-medium mt-0.5 truncate">${escapeHtml(o.customer_name)}</p>` : ''}
                ${actorLine(o.created_by, 'Creado por')}
                ${actorLine(o.paid_by, 'Cobrado por')}
                <p class="text-[9px] text-gray-600 font-bold mt-0.5">${o.paid_at ? localTime(o.paid_at) : ''}</p>
            </div>
            <span class="text-sm font-black text-[#f2460d] tracking-tighter flex-shrink-0">${formatCOP(o.total)}</span>
        </a>
    `).join('');
}

async function loadPending() {
    const list = crEl('pending-list');
    list.innerHTML = '<div class="text-center text-gray-600 text-sm py-6">Cargando…</div>';
    try {
        const res = await fetch('/cash-register/api/pending');
        const body = await res.json();
        if (!res.ok || !body.success) throw new Error(body.error || 'Error');

        if (!body.data.length) {
            list.innerHTML = '<div class="text-center text-gray-600 text-sm py-6">Sin pedidos pendientes de cobro 🎉</div>';
            return;
        }
        list.innerHTML = body.data.map((o) => `
            <div class="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-[#141414] border border-orange-500/10">
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="text-sm font-black text-white tracking-tight">${o.order_number}</span>
                        <span class="px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border border-orange-500/20 text-orange-400">${o.status === 'confirmed' ? 'Confirmado' : 'Pendiente'}</span>
                    </div>
                    ${o.customer_name ? `<p class="text-[11px] text-gray-500 font-medium mt-0.5 truncate">${escapeHtml(o.customer_name)}</p>` : ''}
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <span class="text-sm font-black text-white tracking-tighter">${formatCOP(o.total)}</span>
                    <button onclick="openPaymentModal({ total: ${o.total}, orderId: ${o.id}, mode: 'register', subtitle: '${o.order_number}' })"
                        class="px-3 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase tracking-widest transition-all active:scale-95">
                        Cobrar
                    </button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        list.innerHTML = '<div class="text-center text-red-400 text-sm py-6">No se pudieron cargar los pendientes</div>';
    }
}

async function loadCloses() {
    const list = crEl('closes-list');
    list.innerHTML = '<div class="text-center text-gray-600 text-sm py-6">Cargando…</div>';
    try {
        const res = await fetch('/cash-register/api/closes');
        const body = await res.json();
        if (!res.ok || !body.success) throw new Error(body.error || 'Error');

        if (!body.data.length) {
            list.innerHTML = '<div class="text-center text-gray-600 text-sm py-6">Aún no hay cierres registrados</div>';
            return;
        }
        list.innerHTML = body.data.map((c) => `
            <div class="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-[#141414] border border-[#262626]">
                <div class="flex-1 min-w-0">
                    <p class="text-[11px] font-black text-white tracking-tight">${formatCOP(c.total_sales)} · ${c.total_orders} pedidos</p>
                    <p class="text-[9px] text-gray-600 font-bold mt-0.5">${c.period_start ? localTime(c.period_start) : ''}${c.closed_by ? ' · ' + c.closed_by : ''}</p>
                </div>
                <a href="/cash-register/close/${c.id}/print" target="_blank"
                    class="px-3 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-gray-300 text-[9px] font-black uppercase tracking-widest transition-all flex items-center gap-1">
                    <span class="material-symbols-outlined text-[14px]">print</span>
                    Imprimir
                </a>
            </div>
        `).join('');
    } catch (err) {
        list.innerHTML = '<div class="text-center text-red-400 text-sm py-6">No se pudieron cargar los cierres</div>';
    }
}

/* ── Filtros de rango / método / búsqueda ──────────────────────────────── */

function setRange(key) {
    crState.range = key;
    document.querySelectorAll('.range-btn').forEach((btn) => {
        const active = btn.dataset.range === key;
        btn.className = 'range-btn flex-shrink-0 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-wider transition-all border ' +
            (active
                ? 'bg-[#f2460d] text-white border-[#f2460d] shadow-lg shadow-orange-500/20'
                : 'bg-white/[0.03] text-gray-400 border-white/[0.06] hover:text-white hover:bg-white/[0.06]');
    });
    const customRange = crEl('custom-range');
    if (customRange) customRange.classList.toggle('hidden', key !== 'custom');
    // Limpiar error al salir de custom o al volver a un rango válido
    if (key !== 'custom') {
        const err = crEl('custom-range-error');
        if (err) err.classList.add('hidden');
    }
    // Custom sin fechas → esperar a que el usuario presione "Aplicar" (evita 400)
    if (key === 'custom') {
        if (!crState.customFrom || !crState.customTo) return;
    }
    refresh();
}

function applyCustomRange() {
    crState.customFrom = crEl('custom-from').value;
    crState.customTo = crEl('custom-to').value;
    const err = crEl('custom-range-error');
    if (err) err.classList.add('hidden');

    if (!crState.customFrom || !crState.customTo) {
        if (err) {
            err.textContent = 'Selecciona ambas fechas antes de aplicar.';
            err.classList.remove('hidden');
        }
        return;
    }
    if (crState.customFrom > crState.customTo) {
        if (err) {
            err.textContent = 'La fecha final no puede ser anterior a la inicial.';
            err.classList.remove('hidden');
        }
        return;
    }
    refresh();
}

function selectMethod(method) {
    crState.method = (crState.method === method) ? null : method;
    document.querySelectorAll('.method-card').forEach((card) => {
        const active = crState.method && card.dataset.method === crState.method;
        card.className = 'method-card text-left p-2.5 md:p-4 rounded-xl bg-[#141414] border transition-all active:scale-[0.98] min-w-0 ' +
            (active ? 'border-[#f2460d] ring-1 ring-[#f2460d]/30' : 'border-[#262626] hover:border-[#f2460d]/40');
    });
    const clearBtn = crEl('clear-method-filter');
    if (clearBtn) clearBtn.classList.toggle('hidden', !crState.method);
    refresh();
}

function clearMethodFilter() {
    crState.method = null;
    document.querySelectorAll('.method-card').forEach((card) => {
        card.className = 'method-card text-left p-2.5 md:p-4 rounded-xl bg-[#141414] border border-[#262626] hover:border-[#f2460d]/40 transition-all active:scale-[0.98] min-w-0';
    });
    crEl('clear-method-filter').classList.add('hidden');
    refresh();
}

/* ── Modal de cierre ───────────────────────────────────────────────────── */

function openCloseModal() {
    const subtitle = crEl('close-modal-subtitle');
    const labels = { today: 'Hoy', yesterday: 'Ayer', last_7: 'Últimos 7 días', last_30: 'Últimos 30 días', last_month: 'Mes pasado', this_year: 'Este año', custom: 'Personalizado' };
    subtitle.textContent = labels[crState.range] || 'Personalizado';
    crEl('close-modal-error').classList.add('hidden');
    // Si hay turno abierto, el cierre es del turno (conteo obligatorio en
    // estricto). Si no, es cierre de periodo (conteo solo en estricto).
    renderCloseCounted();
    if (crState.cashStrict && crState.shift) {
        subtitle.textContent += ' · turno abierto';
    }
    document.body.style.overflow = 'hidden';
    crEl('close-modal').classList.remove('hidden');
}

function closeCloseModal() {
    if (crState.requestInFlight) return;
    document.body.style.overflow = '';
    crEl('close-modal').classList.add('hidden');
}

async function confirmClose() {
    if (crState.requestInFlight) return;
    const confirmBtn = crEl('close-confirm');
    const errorEl = crEl('close-modal-error');
    errorEl.classList.add('hidden');

    // Rango personalizado sin fechas → no tiene sentido cerrar ese periodo
    if (crState.range === 'custom' && (!crState.customFrom || !crState.customTo)) {
        errorEl.textContent = 'Selecciona las fechas del rango personalizado en el selector antes de cerrar caja.';
        errorEl.classList.remove('hidden');
        return;
    }
    if (crState.range === 'custom' && crState.customFrom > crState.customTo) {
        errorEl.textContent = 'La fecha final no puede ser anterior a la inicial.';
        errorEl.classList.remove('hidden');
        return;
    }

    // No hay ventas en el periodo → no tiene sentido cerrar caja
    if (crState.summaryAll && crState.summaryAll.total_sales === 0) {
        errorEl.textContent = 'No hay ventas en este periodo, no puedes cerrar caja.';
        errorEl.classList.remove('hidden');
        return;
    }

    // Modo estricto: conteo físico obligatorio solo al cerrar.
    let counted = null;
    if (crState.cashStrict) {
        counted = crParseAmount(crEl('close-counted').value);
        if (counted === null) {
            errorEl.textContent = 'Ingresa el conteo físico del efectivo para cerrar caja.';
            errorEl.classList.remove('hidden');
            return;
        }
    }

    // Con turno abierto el cierre va contra el turno (snapshot del turno
    // para el ticket con esperado/contado/diferencia).
    const closeUrl = (crState.cashStrict && crState.shift) ? '/cash-register/shift/close' : '/cash-register/close';
    const payload = (crState.cashStrict && crState.shift)
        ? { counted_cash: counted }
        : { ...crRangeParams(), ...(counted !== null ? { counted_cash: counted } : {}) };

    crState.requestInFlight = true;
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Cerrando…';

    try {
        const res = await fetch(closeUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': crGetCSRF(),
            },
            body: JSON.stringify(payload),
        });
        const body = await res.json().catch(() => ({}));

        if (res.status === 409) {
            // Solapamiento o duplicado → ya existe un cierre. Mostrar el error
            // y dejar el modal abierto para que el usuario lo lea con calma;
            // solo se refresca el historial para que vea el cierre existente.
            errorEl.textContent = body.error || 'Este periodo ya fue cerrado. Revisa el historial de cierres.';
            errorEl.classList.remove('hidden');
            loadCloses();
            return;
        }
        if (!res.ok) throw new Error(body.error || 'Error al cerrar caja');

        // Éxito → imprimir y recargar
        const printId = body.data.id || body.data.close_id;
        window.open(`/cash-register/close/${printId}/print`, '_blank');
        window.location.reload();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    } finally {
        crState.requestInFlight = false;
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirmar cierre';
    }
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function methodLabel(method) {
    return { cash: 'Efectivo', nequi: 'Nequi', bancolombia: 'Bancolombia', card: 'Tarjeta' }[method] || method;
}

function methodBadgeClasses(method) {
    if (method === 'cash') return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    if (method === 'nequi') return 'bg-pink-500/10 text-pink-400 border-pink-500/20';
    if (method === 'bancolombia') return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    if (method === 'card') return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
}

function localTime(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleString('es-CO', {
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: 'numeric', minute: '2-digit',
        });
    } catch (e) {
        return '';
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function refresh() {
    loadSummary();
    loadOrders();
}

/* ── Turnos de caja (apertura opcional del admin) ─────────────────────── */

function crShiftDiffClass(diff) {
    if (diff === 0) return 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400';
    if (diff > 0) return 'bg-blue-500/10 border border-blue-500/20 text-blue-300';
    return 'bg-red-500/10 border border-red-500/20 text-red-400';
}

function crParseAmount(raw) {
    const n = parseInt(String(raw || '').replace(/\D/g, ''), 10);
    return isNaN(n) ? null : n;
}

async function loadShift() {
    try {
        const res = await fetch('/cash-register/api/shift');
        if (!res.ok) return; // cashier sin permiso u otro rol: no mostrar nada
        const body = await res.json();
        if (!body.success) return;
        crState.shift = body.data.shift;
        crState.shiftExpected = body.data.expected_cash || 0;
        crState.cashStrict = !!body.data.require_cash_shift;
        renderShiftBanner();
        renderCashConfig();
        renderCloseCounted();
    } catch (err) {
        console.error('loadShift:', err);
    }
}

async function loadCashConfig() {
    // Solo el dueño puede leer el flag (403 para cajero → se oculta la tarjeta).
    try {
        const res = await fetch('/cash-register/api/settings');
        if (!res.ok) {
            crEl('cash-config').classList.add('hidden');
            return;
        }
        const body = await res.json();
        if (body.success) {
            crState.cashStrict = !!body.data.require_cash_shift;
            crState.drawerEnabled = !!body.data.drawer_enabled;
            crState.drawerAuto = !!body.data.drawer_auto_open;
            crEl('cash-config').classList.remove('hidden');
            crEl('drawer-card').classList.remove('hidden');
            renderCashConfig();
            renderCloseCounted();
            renderDrawerCard();
            if (typeof Drawer !== 'undefined') Drawer.renderStatus('drawer-status');
        }
    } catch (err) {
        console.error('loadCashConfig:', err);
    }
}

function renderShiftBanner() {
    const banner = crEl('shift-banner');
    if (!banner) return;
    const box = crEl('shift-banner-box');
    const title = crEl('shift-banner-title');
    const sub = crEl('shift-banner-sub');
    const btn = crEl('shift-banner-btn');
    const icon = crEl('shift-banner-icon');
    // Sin modo estricto la apertura es informativa: se muestra igual pero
    // sin bloquear nada (el servidor solo bloquea con el flag activo).
    banner.classList.remove('hidden');
    if (crState.shift) {
        box.className = 'p-4 rounded-2xl border flex items-center justify-between gap-3 bg-emerald-500/[0.06] border-emerald-500/20';
        icon.textContent = 'lock_open';
        icon.className = 'material-symbols-outlined text-[22px] text-emerald-400';
        title.textContent = 'Caja abierta · ' + formatCOP(crState.shiftExpected) + ' esperado';
        sub.textContent = 'Fondo ' + formatCOP(crState.shift.opening_amount) +
            (crState.cashStrict ? ' · modo estricto' : ' · modo flexible');
        btn.textContent = 'Cerrar caja';
        btn.className = 'flex-shrink-0 px-4 py-2.5 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-gray-200 text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 border border-white/[0.08]';
        btn.onclick = () => { openCloseModal(); };
    } else {
        box.className = 'p-4 rounded-2xl border flex items-center justify-between gap-3 ' +
            (crState.cashStrict
                ? 'bg-amber-500/[0.06] border-amber-500/20'
                : 'bg-white/[0.03] border-white/[0.06]');
        icon.textContent = 'point_of_sale';
        icon.className = 'material-symbols-outlined text-[22px] ' + (crState.cashStrict ? 'text-amber-400' : 'text-gray-500');
        title.textContent = 'Caja cerrada';
        sub.textContent = crState.cashStrict
            ? 'El efectivo exige abrir caja primero'
            : 'Sin turno abierto (opcional)';
        btn.textContent = 'Abrir caja';
        btn.className = 'flex-shrink-0 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-black uppercase tracking-widest transition-all active:scale-95';
        btn.onclick = () => { openShiftModal(); };
    }
}

function renderCashConfig() {
    const card = crEl('cash-config');
    const toggle = crEl('cash-config-toggle');
    if (!card || !toggle) return;
    // La tarjeta solo se revela si el GET de settings tuvo éxito (dueño).
    if (card.classList.contains('hidden') && crState.cashStrict !== undefined) {
        // loadCashConfig ya decidió visibilidad; no forzar aquí.
    }
    const on = crState.cashStrict;
    toggle.textContent = on ? 'Activado' : 'Desactivado';
    toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
    toggle.className = 'flex-shrink-0 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 border ' +
        (on
            ? 'bg-emerald-600 text-white border-emerald-600 shadow-lg shadow-emerald-500/20'
            : 'bg-white/[0.05] text-gray-300 border-white/[0.08] hover:bg-white/[0.1]');
}

function renderCloseCounted() {
    const wrap = crEl('close-counted-wrap');
    const row = crEl('close-expected-row');
    if (!wrap || !row) return;
    const strict = crState.cashStrict;
    wrap.classList.toggle('hidden', !strict);
    row.classList.toggle('hidden', !strict);
    const input = crEl('close-counted');
    if (input && !strict) input.value = '';
    if (strict) updateCloseDiff();
}

function updateCloseDiff() {
    const diffEl = crEl('close-diff');
    const expectedEl = crEl('close-expected');
    if (!diffEl || !expectedEl) return;
    // Esperado del turno en vivo si hay uno, si no el neto del periodo.
    let expected = crState.shift ? crState.shiftExpected : 0;
    if (!crState.shift && crState.summaryAll) {
        const cash = crState.summaryAll.breakdown?.cash?.total || 0;
        const change = crState.summaryAll.cash_change_total || 0;
        expected = cash - change;
    }
    expectedEl.textContent = formatCOP(expected);
    const counted = crParseAmount(crEl('close-counted').value);
    if (counted === null) {
        diffEl.classList.add('hidden');
        return;
    }
    const diff = counted - expected;
    diffEl.classList.remove('hidden');
    diffEl.className = 'text-[11px] font-black px-4 py-2.5 rounded-xl ' + crShiftDiffClass(diff);
    diffEl.textContent = diff === 0
        ? 'Cuadre exacto ✓'
        : (diff > 0 ? `Sobrante: ${formatCOP(diff)}` : `Faltante: ${formatCOP(-diff)}`);
}

async function toggleCashStrict() {
    const toggle = crEl('cash-config-toggle');
    toggle.disabled = true;
    try {
        await putCashSettings({ require_cash_shift: !crState.cashStrict });
        loadShift();
    } catch (err) {
        console.error('toggleCashStrict:', err);
    } finally {
        toggle.disabled = false;
    }
}

/* ── Cajón físico (QZ Tray, solo dueño) ───────────────────────────────── */

function crTogglePaint(btn, on, onLabel, offLabel) {
    btn.textContent = on ? onLabel : offLabel;
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.className = 'flex-shrink-0 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 border ' +
        (on
            ? 'bg-emerald-600 text-white border-emerald-600 shadow-lg shadow-emerald-500/20'
            : 'bg-white/[0.05] text-gray-300 border-white/[0.08] hover:bg-white/[0.1]');
}

function renderDrawerCard() {
    const toggle = crEl('drawer-toggle');
    const autoToggle = crEl('drawer-auto-toggle');
    const autoRow = crEl('drawer-auto-row');
    if (!toggle || !autoToggle || !autoRow) return;
    crTogglePaint(toggle, crState.drawerEnabled, 'Activado', 'Desactivado');
    autoRow.classList.toggle('hidden', !crState.drawerEnabled);
    autoRow.classList.toggle('flex', !!crState.drawerEnabled);
    crTogglePaint(autoToggle, crState.drawerAuto, 'Sí', 'No');
}

async function putCashSettings(payload) {
    const res = await fetch('/cash-register/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': crGetCSRF() },
        body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.success) throw new Error(body.error || 'No se pudo guardar');
    crState.cashStrict = !!body.data.require_cash_shift;
    crState.drawerEnabled = !!body.data.drawer_enabled;
    crState.drawerAuto = !!body.data.drawer_auto_open;
    renderCashConfig();
    renderDrawerCard();
    renderCloseCounted();
    renderShiftBanner();
}

async function toggleDrawerEnabled() {
    const btn = crEl('drawer-toggle');
    btn.disabled = true;
    try {
        await putCashSettings({ drawer_enabled: !crState.drawerEnabled });
        if (typeof Drawer !== 'undefined') Drawer.renderStatus('drawer-status');
    } catch (err) {
        console.error('toggleDrawerEnabled:', err);
    } finally {
        btn.disabled = false;
    }
}

async function toggleDrawerAuto() {
    const btn = crEl('drawer-auto-toggle');
    btn.disabled = true;
    try {
        await putCashSettings({ drawer_auto_open: !crState.drawerAuto });
    } catch (err) {
        console.error('toggleDrawerAuto:', err);
    } finally {
        btn.disabled = false;
    }
}

async function testDrawer() {
    if (crState.drawerInFlight || typeof Drawer === 'undefined') return;
    const btn = crEl('drawer-test-btn');
    const result = crEl('drawer-test-result');
    result.classList.add('hidden');
    crState.drawerInFlight = true;
    btn.disabled = true;
    btn.textContent = 'Enviando…';
    try {
        const ok = await Drawer.kick();
        if (!ok) {
            result.classList.remove('hidden');
            result.className = 'text-[11px] font-black px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400';
            result.textContent = 'No se pudo contactar QZ Tray en este PC. Verifica que esté instalado y abierto.';
            return;
        }
        // El cajón no confirma de vuelta: la prueba la hace el humano.
        const opened = window.confirm('Se envió la señal al cajón. ¿Se abrió?');
        result.classList.remove('hidden');
        if (opened) {
            result.className = 'text-[11px] font-black px-4 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400';
            result.textContent = 'Cajón verificado ✓ — el sistema ya puede abrirlo al cobrar.';
        } else {
            result.className = 'text-[11px] font-black px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400';
            result.textContent = 'No se abrió: revisa el cable RJ11 a la impresora (puerto DK) y la impresora por defecto en QZ.';
        }
    } finally {
        crState.drawerInFlight = false;
        btn.disabled = false;
        btn.textContent = 'Probar cajón';
    }
}

function openShiftModal() {
    const err = crEl('shift-modal-error');
    if (err) err.classList.add('hidden');
    const input = crEl('shift-opening');
    if (input) input.value = '';
    document.body.style.overflow = 'hidden';
    crEl('shift-modal').classList.remove('hidden');
    if (input) input.focus();
}

function closeShiftModal() {
    if (crState.shiftInFlight) return;
    document.body.style.overflow = '';
    crEl('shift-modal').classList.add('hidden');
}

async function confirmShiftOpen() {
    if (crState.shiftInFlight) return;
    const btn = crEl('shift-confirm');
    const errEl = crEl('shift-modal-error');
    errEl.classList.add('hidden');
    const opening = crParseAmount(crEl('shift-opening').value) ?? 0;
    if (opening < 0) {
        errEl.textContent = 'El fondo inicial no puede ser negativo.';
        errEl.classList.remove('hidden');
        return;
    }
    crState.shiftInFlight = true;
    btn.disabled = true;
    btn.textContent = 'Abriendo…';
    try {
        const res = await fetch('/cash-register/shift/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': crGetCSRF() },
            body: JSON.stringify({ opening_amount: opening }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok || !body.success) throw new Error(body.error || 'No se pudo abrir caja');
        closeShiftModal();
        loadShift();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.remove('hidden');
    } finally {
        crState.shiftInFlight = false;
        btn.disabled = false;
        btn.textContent = 'Abrir turno';
    }
}

/* ── Init ──────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
    // Range selector
    document.querySelectorAll('.range-btn').forEach((btn) => {
        btn.addEventListener('click', () => setRange(btn.dataset.range));
    });
    // Method cards
    document.querySelectorAll('.method-card').forEach((card) => {
        card.addEventListener('click', () => selectMethod(card.dataset.method));
    });
    // Búsqueda (debounce)
    const searchInput = crEl('search-input');
    if (searchInput) {
        let timer = null;
        searchInput.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                crState.search = searchInput.value.trim();
                loadOrders();
            }, 350);
        });
    }

    const countedInput = crEl('close-counted');
    if (countedInput) {
        countedInput.addEventListener('input', () => {
            countedInput.value = countedInput.value.replace(/[^\d]/g, '');
            updateCloseDiff();
        });
    }
    const openingInput = crEl('shift-opening');
    if (openingInput) {
        openingInput.addEventListener('input', () => {
            openingInput.value = openingInput.value.replace(/[^\d]/g, '');
        });
    }

    refresh();
    loadPending();
    loadCloses();
    loadShift();
    loadCashConfig();
});

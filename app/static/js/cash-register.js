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
    list.innerHTML = orders.map((o) => `
        <a href="/orders/${o.id}" class="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-[#141414] border border-[#262626] hover:border-[#f2460d]/40 transition-all">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                    <span class="text-sm font-black text-white tracking-tight">${o.order_number}</span>
                    <span class="px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border ${methodBadgeClasses(o.payment_method)}">${methodLabel(o.payment_method)}</span>
                </div>
                ${o.customer_name ? `<p class="text-[11px] text-gray-500 font-medium mt-0.5 truncate">${escapeHtml(o.customer_name)}</p>` : ''}
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

    crState.requestInFlight = true;
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Cerrando…';

    try {
        const res = await fetch('/cash-register/close', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': crGetCSRF(),
            },
            body: JSON.stringify(crRangeParams()),
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
        window.open(`/cash-register/close/${body.data.id}/print`, '_blank');
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

    refresh();
    loadPending();
    loadCloses();
});

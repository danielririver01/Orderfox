/**
 * Velzia 2.0.0 — Dashboard Inicio (v3)
 * Hero narrativo: solo actualiza numero grande + delta al cambiar Hoy/Mes.
 * Se elimino Centro de Control Financiero del inicio (queda solo en Caja).
 */

let currentRange = 'today';

document.addEventListener('DOMContentLoaded', () => {
    initStoreToggle();
});

/**
 * Toggle para Abrir/Cerrar Tienda
 */
function initStoreToggle() {
    const storeToggle = document.getElementById('store-toggle');
    if (!storeToggle) return;

    storeToggle.addEventListener('change', async (e) => {
        const isOpen = e.target.checked;
        try {
            const response = await fetch("/dashboard/toggle-status", {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_open: isOpen })
            });

            const data = await response.json();

            if (response.status === 403 && data.error === 'upgrade_required') {
                e.target.checked = !isOpen;
                showToast(data.message, 'error');
                return;
            }

            if (!data.success) throw new Error();

            // Sincronizar Badge de Menu Digital
            updateMenuStatusBadge(isOpen);

        } catch (error) {
            e.target.checked = !isOpen;
            showToast('Error al cambiar estado', 'error');
        }
    });
}

function updateMenuStatusBadge(isOpen) {
    const elements = {
        badge: document.getElementById('menu-status-badge'),
        dot: document.getElementById('menu-status-dot-inner'),
        ping: document.getElementById('menu-status-ping'),
        text: document.getElementById('menu-status-text')
    };

    if (!elements.badge) return;

    if (isOpen) {
        elements.badge.className = "flex items-center gap-2 px-2.5 py-1 rounded-full border flex-shrink-0 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20";
        elements.dot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
        elements.ping.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
        elements.text.className = "text-[9px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-400";
        elements.text.textContent = 'Activo';
    } else {
        elements.badge.className = "flex items-center gap-2 px-2.5 py-1 rounded-full border flex-shrink-0 bg-rose-50 dark:bg-rose-500/10 border-rose-100 dark:border-rose-500/20";
        elements.dot.className = "relative inline-flex rounded-full h-2 w-2 bg-rose-500";
        elements.ping.className = "absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75";
        elements.text.className = "text-[9px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-400";
        elements.text.textContent = 'Inactivo';
    }
}

/**
 * Hero narrativo: actualizar ventas + delta al cambiar Hoy/Mes
 */
window.setDashboardRange = function(range) {
    if (currentRange === range) return;
    currentRange = range;

    // Actualizar botones
    const btnToday = document.getElementById('range-today');
    const btnMonth = document.getElementById('range-month');

    if (range === 'today') {
        btnToday.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all bg-white dark:bg-[#262626] shadow-lg text-black";
        btnMonth.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    } else {
        btnMonth.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all bg-white dark:bg-[#262626] shadow-lg text-black";
        btnToday.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    }

    // Actualizar label
    const heroLabel = document.getElementById('hero-label');
    if (heroLabel) heroLabel.textContent = range === 'today' ? 'HOY LLEVAS' : 'ESTE MES LLEVAS';

    fetchHeroData(range);
};

async function fetchHeroData(range) {
    const salesEl = document.getElementById('hero-sales');
    const deltaEl = document.getElementById('hero-delta');
    const contextEl = document.getElementById('hero-context');
    const ticketEl = document.getElementById('hero-ticket');

    if (!salesEl) return;

    // Loading state
    salesEl.textContent = '...';

    try {
        const resp = await fetch(`/dashboard/api/stats?range=${range}`);
        const data = await resp.json();

        if (!data.success) throw new Error();

        // Numero grande
        salesEl.textContent = formatCurrency(data.total_sales);

        // Delta badge
        if (deltaEl && data.delta_pct !== null && data.delta_pct !== undefined) {
            const arrow = data.delta_pct > 0 ? '\u25B2' : data.delta_pct < 0 ? '\u25BC' : '';
            const colorClass = data.delta_pct > 0 ? 'bg-emerald-500/10 text-emerald-400'
                : data.delta_pct < 0 ? 'bg-rose-500/10 text-rose-400'
                : 'bg-gray-500/10 text-gray-400';
            deltaEl.className = `inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${colorClass}`;
            deltaEl.innerHTML = `${arrow} ${Math.abs(data.delta_pct)}% vs ${range === 'today' ? 'ayer' : 'mes anterior'}`;
            deltaEl.style.display = '';
        } else if (deltaEl) {
            deltaEl.style.display = 'none';
        }

        // Contexto textual
        if (contextEl) {
            if (data.verdict === 'comparativa') {
                contextEl.textContent = `${range === 'today' ? 'Ayer' : 'Mes anterior'} cerro con ${formatCurrency(data.previous_period_sales)} en pedidos`;
            } else if (data.verdict === 'primeras_ventas') {
                contextEl.textContent = '\u{1F195} Primeras ventas del dia!';
            } else if (data.verdict === 'sin_ventas_hoy') {
                contextEl.textContent = `${range === 'today' ? 'Hoy' : 'Este mes'} sin ventas aun.`;
            } else {
                contextEl.textContent = 'Sin ventas registradas aun';
            }
        }

        // Ticket promedio
        if (ticketEl) {
            ticketEl.textContent = data.total_orders > 0
                ? formatCurrency(Math.round(data.total_sales / data.total_orders))
                : '$0';
        }

    } catch (error) {
        console.error('Hero fetch error:', error);
        salesEl.textContent = '$ --';
    }
}

function formatCurrency(value) {
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP',
        maximumFractionDigits: 0
    }).format(value);
}

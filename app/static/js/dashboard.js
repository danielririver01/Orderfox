/**
 * Velzia 2.0.0 — Corazón Financiero
 * Lógica para el Dashboard: Tienda Toggle, Rango de Datos y Sincronización con Scanner IA
 */

let currentRange = 'today';

document.addEventListener('DOMContentLoaded', () => {
    initStoreToggle();
    initFinancialHeart();
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

            // Sincronizar Badge de Menú Digital
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
        elements.badge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full border bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20";
        elements.dot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
        elements.ping.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
        elements.text.className = "text-[10px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-400";
        elements.text.textContent = 'Activo';
    } else {
        elements.badge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full border bg-rose-50 dark:bg-rose-500/10 border-rose-100 dark:border-rose-500/20";
        elements.dot.className = "relative inline-flex rounded-full h-2 w-2 bg-rose-500";
        elements.ping.className = "absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75";
        elements.text.className = "text-[10px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-400";
        elements.text.textContent = 'Inactivo';
    }
}

/**
 * El Corazón Financiero: Hoy vs Mes
 */
function initFinancialHeart() {
    fetchFinancialData();
}

window.setDashboardRange = function(range) {
    if (currentRange === range) return;
    currentRange = range;

    // Actualizar botones
    const btnToday = document.getElementById('range-today');
    const btnMonth = document.getElementById('range-month');

    if (range === 'today') {
        btnToday.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all bg-white dark:bg-[#262626] shadow-sm text-[#f2460d]";
        btnMonth.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all text-gray-400";
    } else {
        btnMonth.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all bg-white dark:bg-[#262626] shadow-sm text-[#f2460d]";
        btnToday.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all text-gray-400";
    }

    fetchFinancialData();
};

async function fetchFinancialData() {
    const ventasEl = document.getElementById('stat-ventas');
    const gastosEl = document.getElementById('stat-gastos');
    const utilityEl = document.getElementById('stat-utilidad');
    const loadingEl = document.getElementById('stat-gastos-loading');

    // Loading states
    // Loading states
    loadingEl.classList.remove('hidden');
    gastosEl.textContent = '...';
    ventasEl.textContent = '$ --';
    utilityEl.textContent = '$ --';
    utilityEl.className = "text-xl font-black tracking-tighter text-gray-300 dark:text-[#262626]";

    try {
        // 1. Fetch Ventas desde Flask API
        const salesResp = await fetch(`/dashboard/api/stats?range=${currentRange}`);
        const salesData = await salesResp.json();
        const sales = salesData.total_sales || 0;

        // 2. Fetch Gastos desde Next.js API (CORS)
        let expenses = 0;
        try {
            const expResp = await fetch(`${SCANNER_IA_URL}/api/stats/summary?range=${currentRange}`, {
                credentials: 'include'
            });
            if (expResp.ok) {
                const expData = await expResp.json();
                expenses = expData.totalExpenses || 0;
            } else {
                gastosEl.textContent = 'N/A';
            }
        } catch (e) {
            console.error('Next.js API unreachable:', e);
            gastosEl.textContent = 'Sin conexión IA';
        }

        // 3. Update UI
        loadingEl.classList.add('hidden');
        ventasEl.textContent = formatCurrency(sales);
        if (expenses > 0) {
            gastosEl.textContent = formatCurrency(expenses);
        }
        
        updateUtilityCard(sales, expenses);

    } catch (error) {
        console.error('Financial fetch error:', error);
        showToast('Error al sincronizar datos financieros', 'error');
    }
}

function updateUtilityCard(sales, expenses) {
    const utility = sales - expenses;
    const utilityEl = document.getElementById('stat-utilidad');
    const cardEl = document.getElementById('utilidad-card');
    const statusEl = document.getElementById('utilidad-status');
    const iconEl = document.getElementById('utilidad-icon');
    const iconBg = document.getElementById('utilidad-icon-bg');

    utilityEl.textContent = formatCurrency(utility);

    if (utility >= 0) {
        // GANANCIA
        cardEl.className = "flex items-center justify-between p-3 rounded-xl bg-emerald-50/50 dark:bg-emerald-500/5 border border-emerald-100/50 dark:border-emerald-500/10 transition-all duration-500 ring-1 ring-emerald-500/20";
        statusEl.textContent = "Balance Positivo";
        statusEl.className = "text-[9px] font-black text-emerald-600 dark:text-emerald-400 uppercase tracking-widest";
        utilityEl.className = "text-xl font-black tracking-tighter text-emerald-600 dark:text-emerald-400";
        iconEl.textContent = "trending_up";
        iconEl.className = "material-symbols-outlined text-emerald-600 text-xl";
        iconBg.className = "w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center transition-colors";
    } else {
        // PÉRDIDA
        cardEl.className = "flex items-center justify-between p-3 rounded-xl bg-rose-50/50 dark:bg-rose-500/5 border border-rose-100/50 dark:border-rose-500/10 transition-all duration-500 animate-[pulse_2s_infinite] ring-1 ring-rose-500/30";
        statusEl.textContent = "Balance Negativo";
        statusEl.className = "text-[9px] font-black text-rose-600 dark:text-rose-400 uppercase tracking-widest";
        utilityEl.className = "text-xl font-black tracking-tighter text-rose-600 dark:text-rose-400";
        iconEl.textContent = "trending_down";
        iconEl.className = "material-symbols-outlined text-rose-600 text-xl";
        iconBg.className = "w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-500/20 flex items-center justify-center transition-colors";
    }
}

function formatCurrency(value) {
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP',
        maximumFractionDigits: 0
    }).format(value);
}
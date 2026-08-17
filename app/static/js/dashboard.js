/**
 * Velzia 2.0.0 — Dashboard Inicio (v4)
 * Hero narrativo + gráficas + top productos + polling 30s.
 * Cobrado_hoy y total_sales vienen del render inicial.
 */

let currentRange = 'today';
let weeklyChart = null;
let revenueChart = null;
let currentChartMode = 'money';
let currentProductsMode = '30d';

document.addEventListener('DOMContentLoaded', () => {
    initStoreToggle();
    initWeeklyChart();
    initRevenueChart();
    fetchTopProducts('30d');
    setInterval(fetchCollectedToday, 30000);
    setInterval(() => {
        initWeeklyChart();
        initRevenueChart();
        fetchTopProducts(currentProductsMode);
    }, 30000);
});

/* ── Store Toggle ────────────────────────────────────────────────────── */

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

/* ── Hero narrativo: actualizar ventas + delta al cambiar Hoy/Mes ───── */

window.setDashboardRange = function(range) {
    if (currentRange === range) return;
    currentRange = range;

    const btnToday = document.getElementById('range-today');
    const btnMonth = document.getElementById('range-month');

    if (range === 'today') {
        btnToday.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all bg-white dark:bg-[#262626] shadow-lg text-black";
        btnMonth.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    } else {
        btnMonth.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all bg-white dark:bg-[#262626] shadow-lg text-black";
        btnToday.className = "px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    }

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

    salesEl.textContent = '...';

    try {
        const resp = await fetch(`/dashboard/api/stats?range=${range}`);
        const data = await resp.json();

        if (!data.success) throw new Error();

        salesEl.textContent = formatCurrency(data.total_sales);

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

/* ── Gráfica barras: ventas semana ──────────────────────────────────── */

function initWeeklyChart() {
    const canvas = document.getElementById('weekly-bar-chart');
    if (!canvas) return;

    fetch('/dashboard/api/weekly-stats')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success || !data.data) return;
            var d = data.data;
            var values = currentChartMode === 'money' ? d.money : d.orders;
            var label = currentChartMode === 'money' ? 'Ventas ($)' : 'Pedidos (#)';
            var color = currentChartMode === 'money' ? '#30A46C' : '#FF7A29';

            if (weeklyChart) {
                weeklyChart.data.labels = d.labels;
                weeklyChart.data.datasets[0].data = values;
                weeklyChart.data.datasets[0].label = label;
                weeklyChart.data.datasets[0].backgroundColor = color;
                weeklyChart.update();
            } else {
                weeklyChart = new Chart(canvas.getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: d.labels,
                        datasets: [{
                            label: label,
                            data: values,
                            backgroundColor: color,
                            borderRadius: 6,
                            borderSkipped: false,
                            maxBarThickness: 32
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: 'rgba(15,15,16,0.9)',
                                titleFont: { weight: 'bold', size: 11 },
                                bodyFont: { size: 11 },
                                padding: 8,
                                cornerRadius: 8,
                                callbacks: {
                                    label: function(ctx) {
                                        return currentChartMode === 'money'
                                            ? formatCurrency(ctx.raw)
                                            : ctx.raw + ' pedidos';
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: '#6B7280', font: { size: 10, weight: 'bold' } }
                            },
                            y: {
                                beginAtZero: true,
                                grid: { color: 'rgba(255,255,255,0.04)' },
                                ticks: {
                                    color: '#6B7280',
                                    font: { size: 10 },
                                    callback: function(v) {
                                        return currentChartMode === 'money'
                                            ? '$' + (v >= 1000 ? (v / 1000) + 'k' : v)
                                            : v;
                                    }
                                }
                            }
                        }
                    }
                });
            }
        })
        .catch(function() {});
}

window.setChartMode = function(mode) {
    if (currentChartMode === mode) return;
    currentChartMode = mode;

    var btnMoney = document.getElementById('chart-mode-money');
    var btnOrders = document.getElementById('chart-mode-orders');

    if (mode === 'money') {
        btnMoney.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all bg-white text-black";
        btnOrders.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    } else {
        btnOrders.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all bg-white text-black";
        btnMoney.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    }

    initWeeklyChart();
};

/* ── Top productos ──────────────────────────────────────────────────── */

function fetchTopProducts(mode) {
    var days = mode === 'today' ? 1 : 30;
    var list = document.getElementById('top-products-list');
    if (!list) return;

    fetch('/dashboard/api/top-products?days=' + days)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success || !data.data || data.data.length === 0) {
                list.innerHTML = '<p class="text-sm font-bold text-gray-500">Sin datos a\u00FAn</p>';
                return;
            }
            var html = '';
            data.data.forEach(function(item, i) {
                html += '<div class="flex items-center justify-between py-2 px-3 rounded-xl bg-white/[0.03] dark:bg-white/[0.02] border border-white/[0.04]">';
                html += '  <div class="flex items-center gap-3 min-w-0">';
                html += '    <span class="text-xs font-black text-gray-500 w-4">' + (i + 1) + '.</span>';
                html += '    <span class="text-xs font-bold text-white truncate">' + item.name + '</span>';
                html += '  </div>';
                html += '  <div class="flex items-center gap-3 flex-shrink-0">';
                html += '    <span class="text-[10px] font-bold text-gray-500">' + item.qty + ' uds</span>';
                html += '    <span class="text-xs font-black text-gray-300">' + formatCurrency(item.revenue) + '</span>';
                html += '  </div>';
                html += '</div>';
            });
            list.innerHTML = html;
        })
        .catch(function() {
            list.innerHTML = '<p class="text-sm font-bold text-gray-500">Error al cargar</p>';
        });
}

window.setProductsMode = function(mode) {
    if (currentProductsMode === mode) return;
    currentProductsMode = mode;

    var btnToday = document.getElementById('products-mode-today');
    var btn30d = document.getElementById('products-mode-30d');

    if (mode === 'today') {
        btnToday.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all bg-white text-black";
        btn30d.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    } else {
        btn30d.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all bg-white text-black";
        btnToday.className = "px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-tighter transition-all text-zinc-500 hover:text-zinc-300";
    }

    fetchTopProducts(mode);
};

/* ── Cobrado hoy (polling) ──────────────────────────────────────────── */

function fetchCollectedToday() {
    fetch('/dashboard/api/collected-today')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success || !data.data) return;
            var el = document.getElementById('hero-collected-today');
            if (el) el.textContent = formatCurrency(data.data.collected);
            var soldEl = document.getElementById('hero-sold-today');
            if (soldEl) soldEl.textContent = formatCurrency(data.data.sold);
        })
        .catch(function() {});
}

/* ── Gráfica línea: tendencia de ingresos 30d ───────────────────────── */

function initRevenueChart() {
    var canvas = document.getElementById('revenue-trend-chart');
    if (!canvas) return;

    fetch('/dashboard/api/revenue-trend')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success || !data.data) return;
            var d = data.data;
            var hasData = d.values.some(function(v) { return v > 0; });

            if (!hasData) {
                if (revenueChart) { revenueChart.destroy(); revenueChart = null; }
                return;
            }

            if (revenueChart) {
                revenueChart.data.labels = d.labels;
                revenueChart.data.datasets[0].data = d.values;
                revenueChart.update();
            } else {
                revenueChart = new Chart(canvas.getContext('2d'), {
                    type: 'line',
                    data: {
                        labels: d.labels,
                        datasets: [{
                            label: 'Ingresos',
                            data: d.values,
                            borderColor: '#FF7A29',
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointHoverBackgroundColor: '#FF7A29',
                            tension: 0.3,
                            fill: false
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: 'rgba(15,15,16,0.9)',
                                titleFont: { weight: 'bold', size: 11 },
                                bodyFont: { size: 11 },
                                padding: 8,
                                cornerRadius: 8,
                                callbacks: {
                                    label: function(ctx) {
                                        return formatCurrency(ctx.raw);
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: {
                                    color: '#6B7280',
                                    font: { size: 9, weight: 'bold' },
                                    maxTicksLimit: 7,
                                    maxRotation: 0
                                }
                            },
                            y: {
                                beginAtZero: true,
                                grid: { color: 'rgba(255,255,255,0.04)' },
                                ticks: {
                                    color: '#6B7280',
                                    font: { size: 10 },
                                    callback: function(v) {
                                        return '$' + (v >= 1000 ? (v / 1000) + 'k' : v);
                                    }
                                }
                            }
                        }
                    }
                });
            }
        })
        .catch(function() {});
}

/* ── Util ───────────────────────────────────────────────────────────── */

function formatCurrency(value) {
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP',
        maximumFractionDigits: 0
    }).format(value);
}

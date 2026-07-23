/* Copilot VZ — cliente de chat conversacional
 * Flujo híbrido: consultas rápidas (gratis) y análisis IA (1 escaneo).
 */
(function () {
    'use strict';

    const API = '/insights/api/conversations';
    let currentConvId = null;
    let currentConvHasMessages = false;
    let welcomeSuggestions = [];
    let isBusy = false;
    const chatCharts = [];

    const $ = (sel) => document.querySelector(sel);
    const messagesEl = $('#messages');
    const inputEl = $('#chat-input');
    const formEl = $('#chat-form');
    const sendBtn = $('#chat-send');
    const convListEl = $('#conv-list');
    const titleEl = $('#conv-title');
    const mainEl = $('#chat-main');

    // ── Modo de pantalla (bienvenida / chat) ────────────
    function setMode(mode) {
        if (!mainEl) return;
        mainEl.classList.toggle('mode-welcome', mode === 'welcome');
        mainEl.classList.toggle('mode-chat', mode === 'chat');
    }

    // ── Utils ───────────────────────────────────────────────
    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // Markdown mínimo y seguro: siempre escapa primero, luego aplica formato.
    function renderMarkdown(src) {
        let s = escapeHtml(src || '');
        s = s
            .replace(/^###\s+(.+)$/gm, '<h3 class="vz-md-h">$1</h3>')
            .replace(/^##\s+(.+)$/gm, '<h2 class="vz-md-h">$1</h2>')
            .replace(/^#\s+(.+)$/gm, '<h1 class="vz-md-h">$1</h1>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/__(.+?)__/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/_(.+?)_/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code class="vz-md-code">$1</code>')
            .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
                '<a href="$2" target="_blank" rel="noopener noreferrer" class="vz-link-orange">$1</a>')
            .replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>')
            .replace(/(<li>[\s\S]*?<\/li>)(?:\s*<li>[\s\S]*?<\/li>)*/g,
                (m) => '<ul class="vz-md-ul">' + m + '</ul>')
            .replace(/\n/g, '<br>');
        return s;
    }

    let _bulkLoading = false;
    function scrollToBottom() {
        if (_bulkLoading) return;
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // ── Aviso "Copilot VZ comete errores" (una vez por conversación) ──
    let disclaimerEl = null;
    let _disclaimerShown = false;
    function buildDisclaimer() {
        const el = document.createElement('div');
        el.className = 'vz-disclaimer';
        el.innerHTML =
            '<span class="material-symbols-outlined text-[14px]" style="color:var(--primary);">info</span>' +
            '<span>AI may produce inaccurate information. Verify critical operational data.</span>';
        return el;
    }
    function removeDisclaimer() {
        if (disclaimerEl && disclaimerEl.parentElement) disclaimerEl.remove();
    }
    function ensureDisclaimer() {
        if (_disclaimerShown) return;
        if (!disclaimerEl) disclaimerEl = buildDisclaimer();
        if (!disclaimerEl.parentElement) messagesEl.appendChild(disclaimerEl);
        _disclaimerShown = true;
    }
    // Inserta un mensaje justo antes del aviso (para que el aviso quede abajo).
    function appendMsg(wrap) {
        if (disclaimerEl && disclaimerEl.parentElement === messagesEl) {
            messagesEl.insertBefore(wrap, disclaimerEl);
        } else {
            messagesEl.appendChild(wrap);
        }
    }

    // ── Date separators ─────────────────────────────────────
    function formatDateLabel(dateStr) {
        if (!dateStr) return '';
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return '';
        const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());
        const diffDays = Math.round((today - dateOnly) / (1000 * 60 * 60 * 24));
        if (diffDays === 0) return 'TODAY';
        if (diffDays === 1) return 'YESTERDAY';
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase();
    }

    function insertDateSeparator(dateStr) {
        const sep = document.createElement('div');
        sep.className = 'vz-date-sep';
        sep.textContent = formatDateLabel(dateStr);
        messagesEl.appendChild(sep);
    }

    // ── Render de burbujas ──────────────────────────────────
    function appendUserBubble(text, id) {
        const wrap = document.createElement('div');
        wrap.className = 'flex flex-col items-end vz-msg-row';
        wrap.dataset.mid = id || '';
        wrap.dataset.role = 'user';
        wrap.innerHTML =
            `<div class="vz-bubble relative max-w-[85%] md:max-w-[70%] text-white text-sm rounded-2xl px-4 py-2.5">
                <div class="vz-bubble-text whitespace-pre-wrap">${escapeHtml(text)}</div>
            </div>
            <div class="vz-msg-actions">
                <button type="button" class="vz-act" data-act="edit" title="Edit message"><span class="material-symbols-outlined">edit</span></button>
            </div>`;
        appendMsg(wrap);
        scrollToBottom();
        return wrap;
    }

    function assistantShell(id, uid) {
        const wrap = document.createElement('div');
        wrap.className = 'flex flex-col items-start vz-msg-row';
        wrap.dataset.mid = id || '';
        wrap.dataset.role = 'assistant';
        wrap.dataset.uid = uid || '';
        wrap.innerHTML =
            `<div class="vz-bubble relative w-full text-white text-sm rounded-2xl px-4 py-3">
                <div class="flex items-center gap-1.5 mb-2">
                    <span class="material-symbols-outlined text-[16px] text-[var(--primary)]">bubble_chart</span>
                    <span class="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Copilot VZ</span>
                    <span class="badge ml-1"></span>
                </div>
                <div class="text-sm leading-relaxed content"></div>
                <div class="extra mt-3"></div>
            </div>
            <div class="vz-msg-actions">
                <button type="button" class="vz-act" data-act="regen" title="Regenerate"><span class="material-symbols-outlined">refresh</span></button>
            </div>`;
        appendMsg(wrap);
        return wrap;
    }

    function fillAssistant(wrap, content, meta, chart) {
        const contentEl = wrap.querySelector('.content');
        contentEl.innerHTML = renderMarkdown(content);
        const badge = wrap.querySelector('.badge');
        if (meta && meta.type === 'quick') {
            badge.className = 'badge text-[10px] font-bold text-[var(--success)] bg-[var(--success)]/10 px-2 py-0.5 rounded-md';
            badge.textContent = 'Quick query';
        } else if (meta && meta.type === 'analysis') {
            badge.className = 'badge vz-badge-orange text-[10px] font-bold px-2 py-0.5 rounded-md';
            const used = meta.credits_used || 0;
            badge.textContent = used > 0 ? 'AI Analysis - 1 credit used' : 'AI Analysis';
        } else if (meta && meta.type === 'scope_guard') {
            badge.className = 'badge text-[10px] font-bold text-sky-300 bg-sky-500/10 px-2 py-0.5 rounded-md';
            badge.textContent = 'Your restaurant only';
        }
        const extra = wrap.querySelector('.extra');
        if (chart) {
            const card = document.createElement('div');
            card.className = 'vz-chart-card-chat';
            const title = chart.title || 'Gráfica';
            card.innerHTML =
                `<div class="vz-chart-card-head">
                    <span class="material-symbols-outlined text-[16px] vz-ic-orange">bar_chart</span>
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="vz-chart-canvas-wrap"><canvas></canvas></div>`;
            extra.appendChild(card);
            const canvas = card.querySelector('canvas');
            const inst = createChart(canvas, chart, true, true);
            chatCharts.push(inst);
            setTimeout(scrollToBottom, 60);
        }
        if (meta && meta.note) {
            const note = document.createElement('div');
            note.className = 'mt-2 text-[11px] text-gray-500 italic leading-relaxed';
            note.textContent = meta.note;
            extra.appendChild(note);
        }
        scrollToBottom();
    }

    // ── Chips de acción que cierran cada respuesta (conversación guiada) ──
    function renderFollowup(wrap, suggestions) {
        if (!suggestions || !suggestions.length) return;
        const extra = wrap.querySelector('.extra');
        if (!extra) return;
        const chipWrap = document.createElement('div');
        chipWrap.className = 'flex flex-wrap gap-2 mt-3';
        suggestions.forEach((s) => {
            const item = (s && typeof s === 'object') ? s : { label: String(s || '') };
            const label = item.label || '';
            const prompt = item.prompt || label;
            const icon = item.icon || '';
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'vz-chip';
            if (icon) {
                const ico = document.createElement('span');
                ico.className = 'material-symbols-outlined text-[14px] mr-1';
                ico.textContent = icon;
                b.appendChild(ico);
            }
            const txt = document.createElement('span');
            txt.textContent = label;
            b.appendChild(txt);
            b.onclick = () => {
                inputEl.value = prompt;
                autoResize();
                sendMessage();
            };
            chipWrap.appendChild(b);
        });
        extra.appendChild(chipWrap);
    }

    // ── Render de gráficas (estilo profesional) ─────────────
    const CHART_FONT = "Outfit, system-ui, -apple-system, 'Segoe UI', sans-serif";
    const CHART_PALETTE = ['#f97316', '#3B82F6', '#10B981', '#A855F7', '#F59E0B', '#EC4899', '#14B8A6'];

    function hexToRgba(hex, a) {
        const h = (hex || '#FF7A1A').replace('#', '');
        const r = parseInt(h.substring(0, 2), 16) || 0;
        const g = parseInt(h.substring(2, 4), 16) || 0;
        const b = parseInt(h.substring(4, 6), 16) || 0;
        return `rgba(${r},${g},${b},${a})`;
    }
    function makeGradient(ctx, color, h) {
        const g = ctx.createLinearGradient(0, 0, 0, h || 300);
        g.addColorStop(0, hexToRgba(color, 0.38));
        g.addColorStop(1, hexToRgba(color, 0.0));
        return g;
    }
    function buildDatasets(chartData, ctx) {
        const ctype = chartData.type || 'line';
        const raw = chartData.datasets || [];
        const datasets = raw.map((d, i) => {
            const color = CHART_PALETTE[i % CHART_PALETTE.length];
            const data = Array.isArray(d.data)
                ? d.data.filter((v) => typeof v === 'number' && !isNaN(v))
                : [];
            const base = {
                label: d.label || `Serie ${i + 1}`,
                data,
                borderColor: color,
                backgroundColor: color,
                tension: 0.35,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 2,
            };
            if (ctype === 'line') {
                base.fill = true;
                base.backgroundColor = makeGradient(ctx, color, 300);
            } else if (ctype === 'bar') {
                base.fill = false;
                base.backgroundColor = hexToRgba(color, 0.85);
                base.borderWidth = 0;
                base.borderRadius = 6;
            }
            return base;
        });
        if ((ctype === 'doughnut' || ctype === 'pie') && datasets[0]) {
            const sliceColors = (raw[0].data || []).map((_, i) => CHART_PALETTE[i % CHART_PALETTE.length]);
            datasets[0] = Object.assign(datasets[0], {
                backgroundColor: sliceColors,
                borderColor: '#0c0c0f',
                borderWidth: 2,
                hoverOffset: 8,
            });
        }
        return datasets;
    }
    function createChart(canvas, chartData, responsive, showTitle) {
        const ctx = canvas.getContext('2d');
        const ctype = chartData.type || 'line';
        const labels = (chartData.labels || [])
            .filter((l) => l !== null && l !== undefined)
            .map(String);
        const datasets = buildDatasets(chartData, ctx);
        const isPie = ctype === 'doughnut' || ctype === 'pie';
        return new Chart(ctx, {
            type: ctype,
            data: { labels, datasets },
            options: {
                responsive: responsive !== false,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    title: {
                        display: showTitle !== false && !!chartData.title,
                        text: chartData.title,
                        color: '#e5e5e5',
                        font: { family: CHART_FONT, size: 14, weight: '700' },
                        padding: { bottom: 12 },
                    },
                    legend: {
                        position: isPie ? 'bottom' : 'top',
                        labels: {
                            color: '#c9c9c9',
                            font: { family: CHART_FONT, size: 12 },
                            usePointStyle: true,
                            pointStyle: 'circle',
                            boxWidth: 8,
                            padding: 16,
                        },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(18,18,22,0.96)',
                        titleColor: '#ffffff',
                        bodyColor: '#e5e5e5',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 8,
                        displayColors: true,
                        usePointStyle: true,
                        titleFont: { family: CHART_FONT },
                        bodyFont: { family: CHART_FONT },
                    },
                },
                scales: isPie ? {} : {
                    x: {
                        ticks: { color: '#8a8a8a', font: { family: CHART_FONT, size: 11 } },
                        grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                        border: { display: false },
                    },
                    y: {
                        ticks: { color: '#8a8a8a', font: { family: CHART_FONT, size: 11 } },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        border: { display: false },
                        beginAtZero: true,
                    },
                },
            },
        });
    }
    function destroyChatCharts() {
        chatCharts.forEach((c) => { try { c.destroy(); } catch (e) { /* noop */ } });
        chatCharts.length = 0;
    }

    // ── Tarjeta de "sin créditos" (flujo interrumpido) ──────
    function showNoCreditsCard(canBuy) {
        const wrap = document.createElement('div');
        wrap.className = 'flex justify-start';
        if (canBuy) {
            wrap.innerHTML =
                `<div class="max-w-[90%] rounded-2xl px-4 py-3" style="background:var(--bg-card-alt);">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="material-symbols-outlined text-[18px] text-[var(--primary)]">bolt</span>
                        <span class="text-sm font-bold text-white">Need more AI credits</span>
                    </div>
                    <p class="text-xs" style="color:var(--text-muted)">Top up your AI credits and keep getting insights from your data.</p>
                    <button id="ob-buy-credits" class="vz-btn-primary inline-flex items-center gap-1.5 px-4 py-1.5 text-xs mt-2">
                        <span class="material-symbols-outlined text-[15px]">bolt</span> Top up AI credits
                    </button>
                </div>`;
        } else {
            wrap.innerHTML =
                `<div class="max-w-[90%] rounded-2xl px-4 py-3" style="background:var(--bg-card-alt);">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="material-symbols-outlined text-[18px] text-[var(--error)]">block</span>
                        <span class="text-sm font-bold text-white">No AI credits</span>
                    </div>
                    <p class="text-xs" style="color:var(--text-muted)">Your trial is ending. Activate a plan to keep using AI analysis.</p>
                    <a href="/dashboard/subscription" class="vz-btn-primary inline-flex items-center gap-1.5 px-4 py-1.5 text-xs mt-2">View plans</a>
                </div>`;
        }
        appendMsg(wrap);
        if (canBuy) {
            const btn = wrap.querySelector('#ob-buy-credits');
            if (btn && typeof window.openTokenModal === 'function') {
                btn.addEventListener('click', () => window.openTokenModal());
            }
        }
        scrollToBottom();
    }

    // Suscripción vencida tras la gracia: créditos congelados, debe activar plan.
    function showSubscriptionRequiredCard(message) {
        const wrap = document.createElement('div');
        wrap.className = 'flex justify-start';
        const msg = escapeHtml(
            message || 'Your trial has ended. Your credits are saved. Activate a plan to use them.');
        wrap.innerHTML =
            `<div class="max-w-[90%] rounded-2xl px-4 py-3" style="background:var(--bg-card-alt);">
                <div class="flex items-center gap-2 mb-1">
                    <span class="material-symbols-outlined text-[18px] text-[var(--error)]">lock</span>
                    <span class="text-sm font-bold text-white">Trial ended</span>
                </div>
                <p class="text-xs" style="color:var(--text-muted);">${msg}</p>
                <a href="/dashboard/subscription" class="vz-btn-primary inline-flex items-center gap-1.5 px-4 py-1.5 text-xs mt-2">Activate plan</a>
            </div>`;
        appendMsg(wrap);
        scrollToBottom();
    }

    // ── Llamadas API ───────────────────────────────────────
    async function apiGet(url) {
        const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
        return r.json();
    }
    async function apiSend(url, body) {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body),
        });
        return r.json();
    }
    async function apiPatch(url, body) {
        const r = await fetch(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body),
        });
        return r.json();
    }
    async function apiDelete(url) {
        const r = await fetch(url, {
            method: 'DELETE',
            headers: { 'Accept': 'application/json' },
        });
        return r.json();
    }

    let allConversations = [];
    let convSearchTerm = '';

    function normalizeStr(s) {
        return (s || '').toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
    }

    function buildConvItem(c) {
        const item = document.createElement('div');
        item.className = 'conv-item w-full text-left px-3 py-2.5 rounded-xl' +
            (c.id === currentConvId ? ' active' : '');
        item.dataset.cid = c.id;
        item.innerHTML =
            `<span class="material-symbols-outlined text-[16px]" style="color:${c.pinned ? 'var(--primary)' : 'var(--text-dim)'}">${c.pinned ? 'push_pin' : 'description'}</span>
             <span class="flex-1 min-w-0 truncate text-xs font-medium" style="color:var(--text-muted)">${escapeHtml(c.title || 'Untitled analysis')}</span>
             ${c.pinned ? '<span class="vz-pin-dot"></span>' : ''}
             <button class="vz-kebab" data-kebab title="More options" aria-label="More options"><span class="material-symbols-outlined">more_vert</span></button>`;
        item.onclick = () => selectConversation(c.id);
        item.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            openConvMenu(c, e.clientX, e.clientY);
        });
        const kebab = item.querySelector('[data-kebab]');
        kebab.addEventListener('click', (e) => {
            e.stopPropagation();
            const r = e.currentTarget.getBoundingClientRect();
            openConvMenu(c, r.left, r.bottom + 4);
        });
        return item;
    }

    function renderConversations() {
        hideConvSkeleton();
        const term = normalizeStr(convSearchTerm);
        const list = term
            ? allConversations.filter((c) => normalizeStr(c.title || 'Untitled analysis').includes(term))
            : allConversations;
        convListEl.innerHTML = '';
        const emptyState = document.getElementById('conv-empty-state');
        if (!list.length) {
            if (term) {
                // Searching but no results → show inline text
                if (emptyState) emptyState.hidden = true;
                convListEl.style.display = '';
                const empty = document.createElement('div');
                empty.className = 'vz-conv-empty';
                empty.textContent = 'No results';
                convListEl.appendChild(empty);
            } else {
                // No conversations at all → show fancy empty state
                convListEl.style.display = 'none';
                if (emptyState) emptyState.hidden = false;
            }
            return;
        }
        // We have items → show list, hide empty state
        convListEl.style.display = '';
        if (emptyState) emptyState.hidden = true;
        list.forEach((c) => convListEl.appendChild(buildConvItem(c)));
    }

    function hideConvSkeleton() {
        const skel = document.getElementById('conv-list-skeleton');
        if (skel) skel.style.display = 'none';
    }
    function showConvSkeleton() {
        const skel = document.getElementById('conv-list-skeleton');
        if (skel) skel.style.display = '';
        const emptyState = document.getElementById('conv-empty-state');
        if (emptyState) emptyState.hidden = true;
    }

    async function loadConversations() {
        showConvSkeleton();
        try {
            const data = await apiGet(API);
            if (!data.success) {
                console.warn('[Copilot VZ] loadConversations: API returned success=false', data);
                showConvError('No se pudieron cargar las conversaciones.');
                return;
            }
            allConversations = data.data || [];
            renderConversations();
        } catch (e) {
            console.warn('[Copilot VZ] loadConversations: fetch failed', e);
            showConvError('Error de conexión al cargar conversaciones.');
        }
    }

    function showConvError(msg) {
        const list = document.getElementById('conv-list');
        const emptyState = document.getElementById('conv-empty-state');
        if (!list) return;
        convListEl.innerHTML = '';
        convListEl.style.display = '';
        if (emptyState) emptyState.hidden = true;
        const errEl = document.createElement('div');
        errEl.className = 'vz-conv-error';
        errEl.innerHTML = '<span class="material-symbols-outlined block">cloud_off</span>' +
            '<span>' + escapeHtml(msg) + '</span>';
        convListEl.appendChild(errEl);
    }

    function saveConvToStorage(id) {
        try { localStorage.setItem('vz_last_conv', id); } catch (e) {}
    }

    function showLoadingMessages() {
        const overlay = document.getElementById('chat-loading-overlay');
        if (overlay) overlay.classList.add('active');
        if (messagesEl) messagesEl.style.display = 'none';
    }
    function hideLoadingMessages() {
        const overlay = document.getElementById('chat-loading-overlay');
        if (overlay) overlay.classList.remove('active');
        if (messagesEl) messagesEl.style.display = '';
    }

    async function selectConversation(id) {
        currentConvId = id;
        _disclaimerShown = false;
        saveConvToStorage(id);
        removeTypingIndicator();
        loadConversations();
        closeConvDrawer();
        showLoadingMessages();
        try {
            const data = await apiGet(`${API}/${id}`);
            hideLoadingMessages();
            if (!data.success) {
                console.warn('[Copilot VZ] selectConversation: API returned success=false', data);
                saveConvToStorage(null);
                showEmptyState();
                return;
            }
            destroyChatCharts();
            messagesEl.innerHTML = '';
            const conv = data.data;
            titleEl.textContent = conv.title || 'New analysis';
            currentConvHasMessages = !!(conv.messages && conv.messages.length);
            updateHeaderButtons();
            updateContextRing(data.context_usage !== undefined ? data.context_usage : 0);
            if (!conv.messages.length) {
                showEmptyState();
                setMode('welcome');
            } else {
                setMode('chat');
                _disclaimerShown = true;
                _bulkLoading = true;
                let lastUserId = null;
                let lastDate = null;
                conv.messages.forEach((m) => {
                    // Insert date separator
                    const msgDate = m.created_at || m.timestamp;
                    if (msgDate) {
                        const msgDay = new Date(msgDate).toDateString();
                        if (msgDay !== lastDate) {
                            lastDate = msgDay;
                            insertDateSeparator(msgDate);
                        }
                    }
                    if (m.role === 'user') {
                        lastUserId = m.id;
                        appendUserBubble(m.content, m.id);
                    } else {
                        const meta = m.metadata || {};
                        if (meta.type === 'empty_state') {
                            renderEmptyState(meta);
                        } else {
                            const wrap = assistantShell(m.id, lastUserId);
                            fillAssistant(wrap, m.content, meta, meta.chart);
                        }
                    }
                });
                _bulkLoading = false;
                ensureDisclaimer();
                requestAnimationFrame(() => scrollToBottom());
            }
        } catch (e) {
            hideLoadingMessages();
            console.warn('[Copilot VZ] selectConversation: fetch failed', e);
            saveConvToStorage(null);
            showEmptyState();
        }
    }

    async function showEmptyState() {
        removeDisclaimer();
        messagesEl.innerHTML = '';
        // Check for onboarding guidance for new users.
        const ob = await fetchOnboarding();
        if (ob && ob.card) {
            setMode('chat');
            renderOnboardingCard(ob.card);
            return;
        }
        setMode('welcome');
        // Carga sugerencias dinámicas desde el backend (sin crear chat si ya hay uno activo).
        if (!currentConvId) {
            try {
                const data = await apiSend(`${API}/draft`, {});
                if (data && data.success && data.data) {
                    currentConvId = data.data.id;
                    renderWelcomeChips(data.data.welcome_suggestions || []);
                }
            } catch (e) { /* silencioso */ }
        }
    }

    // ── Chips de bienvenida dinámicos (desde el backend) ──
    function renderWelcomeChips(suggestions) {
        welcomeSuggestions = Array.isArray(suggestions) ? suggestions : [];
        const wrap = $('#welcome-chips');
        if (!wrap) return;
        wrap.innerHTML = '';
        suggestions.forEach((s) => {
            const item = (s && typeof s === 'object') ? s : { label: String(s || ''), prompt: String(s || '') };
            const label = item.label || item.prompt || '';
            const prompt = item.prompt || item.label || '';
            if (!label) return;
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'vz-chip';
            b.textContent = label;
            b.onclick = () => {
                inputEl.value = prompt;
                autoResize();
                sendMessage();
            };
            wrap.appendChild(b);
        });
    }

    // Tipos de estado vacío que forman parte del onboarding interactivo.
    const ONBOARDING_TYPES = new Set(['no_catalog', 'no_sales_yet']);

    // Construye la tarjeta de estado vacío / onboarding. Las sugerencias pueden
    // ser: acción inline (crear categoría/producto/pedido), link real, o chip
    // que reenvía el texto al chat.
    function buildOnboardingCard(state) {
        const prev = document.getElementById('ob-card');
        if (prev) prev.remove();
        const wrap = document.createElement('div');
        wrap.className = 'flex justify-start';
        if (ONBOARDING_TYPES.has(state.type)) wrap.id = 'ob-card';
        const icon = escapeHtml(state.icon || 'insights');
        const text = escapeHtml(state.text || '').replace(/\n/g, '<br>');
        const chips = (state.suggestions || []).map((s) => {
            const label = escapeHtml(s.label || '');
            if (s.action) {
                return `<button class="vz-onb-action" data-action="${escapeHtml(s.action)}">${label}<span class="material-symbols-outlined text-[15px]">arrow_forward</span></button>`;
            }
            if (s.href) {
                return `<a href="${escapeHtml(s.href)}" class="px-3 py-1.5 rounded-xl text-xs font-bold inline-flex items-center gap-1" style="color:var(--primary);background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.2);">${label}<span class="material-symbols-outlined text-[14px]">open_in_new</span></a>`;
            }
            return `<button class="esg-chip px-3 py-1.5 rounded-xl text-xs font-bold" data-sugg="${label}" style="color:var(--primary);background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.2);">${label}</button>`;
        }).join('');
        wrap.innerHTML =
            `<div class="max-w-[92%] rounded-2xl px-4 py-4" style="background:var(--bg-card-alt);">
                <div class="flex items-center gap-3 mb-2">
                    <span class="w-10 h-10 rounded-xl flex items-center justify-center" style="background:rgba(249,115,22,0.10);">
                        <span class="material-symbols-outlined text-[22px]" style="color:var(--primary);">${icon}</span>
                    </span>
                    <span class="text-[11px] font-bold" style="color:var(--text-muted); text-transform:uppercase; letter-spacing:0.1em;">Copilot VZ</span>
                </div>
                <div class="text-sm leading-relaxed whitespace-pre-wrap" style="color:var(--text-main);">${text}</div>
                ${chips ? `<div class="flex flex-wrap gap-2 mt-3">${chips}</div>` : ''}
            </div>`;
        return wrap;
    }

    function wireOnboardingCard(wrap) {
        wrap.querySelectorAll('.vz-onb-action').forEach((btn) => {
            btn.addEventListener('click', () => openOnbModal(btn.dataset.action));
        });
        wrap.querySelectorAll('.esg-chip').forEach((chip) => {
            chip.addEventListener('click', () => {
                inputEl.value = chip.dataset.sugg;
                autoResize();
                sendMessage();
            });
        });
    }

    // Tarjeta de onboarding que reemplaza la bienvenida para usuarios nuevos.
    function renderOnboardingCard(state) {
        const wrap = buildOnboardingCard(state);
        messagesEl.appendChild(wrap);
        wireOnboardingCard(wrap);
        scrollToBottom();
        return wrap;
    }

    // Mensaje de cierre cuando el usuario ya completó el onboarding.
    function appendOnboardingDone() {
        const wrap = document.createElement('div');
        wrap.className = 'flex justify-start';
        wrap.innerHTML =
            `<div class="max-w-[92%] rounded-2xl px-4 py-4" style="background:var(--bg-card-alt);">
                <div class="flex items-center gap-3 mb-2">
                    <span class="w-10 h-10 rounded-xl flex items-center justify-center" style="background:rgba(16,185,129,0.10);">
                        <span class="material-symbols-outlined text-[22px]" style="color:#34d399">check_circle</span>
                    </span>
                    <span class="text-[11px] font-bold" style="color:var(--text-muted); text-transform:uppercase; letter-spacing:0.1em;">Copilot VZ</span>
                </div>
                <div class="text-sm leading-relaxed whitespace-pre-wrap" style="color:var(--text-main);">¡Listo! Ya tienes lo básico para empezar. Pregúntame lo que quieras sobre tu negocio.</div>
            </div>`;
        messagesEl.appendChild(wrap);
        scrollToBottom();
    }

    // Estado vacío inteligente (sin datos): tarjeta bonita + sugerencias clicables.
    function renderEmptyState(state) {
        removeDisclaimer();
        const wrap = buildOnboardingCard(state);
        messagesEl.appendChild(wrap);
        wireOnboardingCard(wrap);
        scrollToBottom();
        return wrap;
    }

    async function newConversation() {
        try {
            const data = await apiSend(`${API}/draft`, {});
            if (!data.success) {
                console.warn('[Copilot VZ] newConversation: API returned success=false', data);
                return;
            }
            destroyChatCharts();
            messagesEl.innerHTML = '';
            _disclaimerShown = false;
            showEmptyState();
            updateContextRing(0);
            currentConvId = data.data.id;
            renderWelcomeChips(data.data.welcome_suggestions || []);
            saveConvToStorage(null);
            currentConvHasMessages = false;
            updateHeaderButtons();
            titleEl.textContent = 'New analysis';
            await loadConversations();
            closeConvDrawer();
        } catch (e) {
            console.warn('[Copilot VZ] newConversation: fetch failed', e);
        }
    }

    // ── Envío ──────────────────────────────────────────────
    function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || isBusy) return;
        if (!currentConvId) { newConversationThenSend(text); return; }
        proceedSend(text, currentConvId, null);
    }

    async function newConversationThenSend(text) {
        try {
            const data = await apiSend(`${API}/draft`, {});
            if (!data.success) {
                console.warn('[Copilot VZ] newConversationThenSend: API returned success=false', data);
                return;
            }
            currentConvId = data.data.id;
            _disclaimerShown = false;
            titleEl.textContent = 'New analysis';
            await loadConversations();
            proceedSend(text, currentConvId, null);
        } catch (e) {
            console.warn('[Copilot VZ] newConversationThenSend: fetch failed', e);
        }
    }

    let typingIndicator = null;

    function showTypingIndicator() {
        removeTypingIndicator();
        const wrap = document.createElement('div');
        wrap.className = 'flex flex-col items-start vz-msg-row';
        wrap.id = 'typing-indicator';
        wrap.innerHTML =
            `<div class="vz-bubble relative rounded-2xl px-3 py-2.5" style="background:var(--bg-card-alt);">
                <div class="flex items-center gap-1.5 mb-0.5">
                    <span class="material-symbols-outlined text-[13px] text-[var(--primary)]">bubble_chart</span>
                    <span class="text-[10px] font-bold" style="color:var(--text-muted); text-transform:uppercase; letter-spacing:0.1em;">Copilot VZ</span>
                </div>
                <div class="vz-typing-dots">
                    <span class="vz-dot"></span>
                    <span class="vz-dot"></span>
                    <span class="vz-dot"></span>
                </div>
            </div>`;
        appendMsg(wrap);
        scrollToBottom();
        typingIndicator = wrap;
    }

    function removeTypingIndicator() {
        if (typingIndicator && typingIndicator.parentElement) {
            typingIndicator.remove();
        }
        typingIndicator = null;
    }

    async function proceedSend(text, convId, messageId) {
        isBusy = true;
        sendBtn.disabled = true;
        setMode('chat');
        const empty = document.getElementById('empty-state');
        if (empty) empty.remove();
        const userWrap = appendUserBubble(text);
        showTypingIndicator();
        currentConvHasMessages = true;
        updateHeaderButtons();
        ensureDisclaimer();
        inputEl.value = '';
        autoResize();
        try {
            const body = { content: text };
            if (messageId) body.message_id = messageId;
            const data = await apiSend(`${API}/${convId}/messages`, body);
            removeTypingIndicator();
            if (userWrap && data && data.message_id) userWrap.dataset.mid = data.message_id;
            handleResponse(data, text);
        } catch (e) {
            removeTypingIndicator();
            appendError('Could not connect to Copilot VZ. Please try again.');
        } finally {
            isBusy = false;
            sendBtn.disabled = false;
        }
    }

    function updateContextFromResponse(data) {
        if (data.context_usage !== undefined) {
            updateContextRing(data.context_usage);
        }
        if (data.context_optimized) {
            showToast('🧠 Organized our conversation to keep what matters most and continue responding with full context.');
        }
    }

    function handleResponse(data, originalText) {
        if (!data || !data.success) {
            appendError((data && data.message) || 'An unexpected error occurred.');
            return;
        }
        if (data.is_empty_state) {
            renderEmptyState(data.empty_state);
            updateContextFromResponse(data);
            return;
        }
        const meta = data.metadata || {};
        if (data.type === 'quick') {
            const wrap = assistantShell(data.assistant_message_id, data.message_id);
            fillAssistant(wrap, data.content, meta, data.chart);
            renderFollowup(wrap, data.suggestions);
        } else if (data.type === 'subscription_required') {
            removeTypingIndicator();
            showSubscriptionRequiredCard(data.message);
        } else if (data.type === 'no_credits') {
            removeTypingIndicator();
            showNoCreditsCard(data.can_buy);
        } else if (data.type === 'analysis') {
            const wrap = assistantShell(data.assistant_message_id, data.message_id);
            fillAssistant(wrap, data.content, meta, data.chart);
            renderFollowup(wrap, data.suggestions);
            loadConversations();
        } else if (data.type === 'scope_guard') {
            const wrap = assistantShell(data.assistant_message_id, data.message_id);
            fillAssistant(wrap, data.content, meta, null);
            renderFollowup(wrap, data.suggestions);
        } else if (data.type === 'llm_error' || data.type === 'error') {
            removeTypingIndicator();
            appendError(data.message || 'AI service error.');
        }
        updateContextFromResponse(data);
    }

    function appendError(msg) {
        const wrap = document.createElement('div');
        wrap.className = 'flex justify-start';
        wrap.innerHTML =
            `<div class="max-w-[90%] rounded-2xl px-4 py-2.5 text-xs" style="background:var(--bg-card-alt);color:var(--error);">${escapeHtml(msg)}</div>`;
        appendMsg(wrap);
        scrollToBottom();
    }

    // ── Editar mensaje enviado / Regenerar respuesta ────────
    function setBusyBtn(btn, busy) {
        if (!btn) return;
        btn.disabled = !!busy;
        btn.classList.toggle('is-busy', !!busy);
    }

    function startEdit(wrap, btn) {
        if (wrap.dataset.editing) return;
        const textEl = wrap.querySelector('.vz-bubble-text');
        if (!textEl) return;
        const mid = wrap.dataset.mid;
        const original = textEl.textContent;
        wrap.dataset.editing = '1';
        if (btn) btn.style.visibility = 'hidden';
        const ta = document.createElement('textarea');
        ta.className = 'vz-edit-area';
        ta.value = original;
        const bar = document.createElement('div');
        bar.className = 'vz-edit-bar';
        bar.innerHTML =
            '<button type="button" class="vz-edit-cancel px-3 py-1.5 rounded-xl text-xs font-bold text-gray-400 hover:bg-white/5 transition">Cancelar</button>' +
            '<button type="button" class="vz-edit-save vz-btn-primary px-4 py-1.5 text-xs">Guardar</button>';
        textEl.replaceWith(ta);
        ta.after(bar);
        ta.focus();
        ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
        bar.querySelector('.vz-edit-cancel').onclick = () => selectConversation(currentConvId);
        bar.querySelector('.vz-edit-save').onclick = () => {
            const nv = ta.value.trim();
            if (!nv) { selectConversation(currentConvId); return; }
            if (btn) btn.style.visibility = '';
            wrap.dataset.editing = '';
            doEdit(mid, nv, btn);
        };
    }

    async function doEdit(mid, content, btn) {
        if (!currentConvId) return;
        setBusyBtn(btn, true);
        try {
            const data = await apiSend(`${API}/${currentConvId}/messages`, {
                content: content,
                message_id: mid,
                replace_tail: true,
            });
            if (!data || !data.success) {
                appendError((data && data.message) || 'Could not edit the message.');
                await selectConversation(currentConvId);
                return;
            }
            await selectConversation(currentConvId);
        } catch (e) {
            appendError('Could not edit the message.');
        } finally {
            setBusyBtn(btn, false);
        }
    }

    async function regenerate(wrap, btn) {
        const uid = wrap.dataset.uid;
        if (!uid || !currentConvId || isBusy) return;
        wrap.remove();
        setBusyBtn(btn, true);
        showTypingIndicator();
        try {
            const data = await apiSend(`${API}/${currentConvId}/messages`, {
                content: '',
                message_id: uid,
                replace_tail: true,
            });
            removeTypingIndicator();
            if (!data || !data.success) {
                appendError((data && data.message) || 'Could not regenerate the response.');
                return;
            }
            await selectConversation(currentConvId);
        } catch (e) {
            removeTypingIndicator();
            appendError('Could not regenerate the response.');
        } finally {
            setBusyBtn(btn, false);
        }
    }

    messagesEl.addEventListener('click', (e) => {
        const actBtn = e.target.closest('.vz-act');
        if (!actBtn) return;
        const wrap = actBtn.closest('[data-role]');
        if (!wrap) return;
        const act = actBtn.dataset.act;
        if (act === 'edit') startEdit(wrap, actBtn);
        else if (act === 'regen') regenerate(wrap, actBtn);
    });

    // ── Input UX ───────────────────────────────────────────
    function autoResize() {
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 144) + 'px';
    }

    // ── Eventos ────────────────────────────────────────────
    formEl.addEventListener('submit', (e) => { e.preventDefault(); sendMessage(); });
    inputEl.addEventListener('input', autoResize);
    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    // ── Cajón de conversaciones (drawer) ────────────────
    function openConvDrawer() {
        $('#conv-panel').classList.add('open');
        $('#conv-backdrop').classList.add('open');
    }
    function closeConvDrawer() {
        $('#conv-panel').classList.remove('open');
        $('#conv-backdrop').classList.remove('open');
    }

    document.querySelectorAll('#btn-new-conv').forEach(function(el) {
        el.addEventListener('click', newConversation);
    });

    $('#btn-toggle-conv').addEventListener('click', () => {
        if ($('#conv-panel').classList.contains('open')) closeConvDrawer();
        else openConvDrawer();
    });
    $('#conv-backdrop').addEventListener('click', closeConvDrawer);
    // ── Modal de renombrado (moderno, estilo ChatGPT) ──
    const renameModal = $('#rename-modal');
    const renameInput = $('#rename-input');
    let renameTargetId = null;
    function openRenameModal(cid, currentTitle) {
        if (!cid) return;
        renameTargetId = cid;
        renameInput.value = (currentTitle && currentTitle !== 'New analysis') ? currentTitle : '';
        renameModal.hidden = false;
        setTimeout(() => { renameInput.focus(); renameInput.select(); }, 30);
    }
    function closeRenameModal() { renameModal.hidden = true; renameTargetId = null; }
    async function saveRename() {
        const nv = renameInput.value.trim();
        const cid = renameTargetId;
        if (!nv || !cid) { closeRenameModal(); return; }
        try {
            await fetch(`${API}/${cid}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ title: nv }),
            });
            if (cid === currentConvId) titleEl.textContent = nv;
            loadConversations();
        } catch (e) { /* silencioso */ }
        closeRenameModal();
    }
    $('#btn-edit-title').addEventListener('click', () => openRenameModal(currentConvId, titleEl.textContent));
    $('#rename-cancel').addEventListener('click', closeRenameModal);
    $('#rename-save').addEventListener('click', saveRename);
    renameModal.addEventListener('click', (e) => { if (e.target === renameModal) closeRenameModal(); });
    renameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); saveRename(); }
        if (e.key === 'Escape') { e.preventDefault(); closeRenameModal(); }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !renameModal.hidden) closeRenameModal();
    });

    // ── Menú contextual de conversación (clic derecho) ──
    const convMenu = $('#conv-menu');
    const ctxPinLabel = $('#ctx-pin-label');
    let menuTarget = null;
    function openConvMenu(c, x, y) {
        menuTarget = c;
        ctxPinLabel.textContent = c.pinned ? 'Quitar de fijados' : 'Fijar conversación';
        convMenu.hidden = false;
        const mw = convMenu.offsetWidth, mh = convMenu.offsetHeight;
        if (x + mw > window.innerWidth - 8) x = window.innerWidth - mw - 8;
        if (y + mh > window.innerHeight - 8) y = window.innerHeight - mh - 8;
        convMenu.style.left = Math.max(8, x) + 'px';
        convMenu.style.top = Math.max(8, y) + 'px';
    }
    function closeConvMenu() { convMenu.hidden = true; menuTarget = null; }
    convMenu.querySelectorAll('.vz-ctx-item').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const action = btn.dataset.action;
            const c = menuTarget;
            closeConvMenu();
            if (!c) return;
            if (action === 'pin') {
                try {
                    const res = await apiPatch(`${API}/${c.id}/pin`, { pinned: !c.pinned });
                    if (!res.success && res.error_code === 'PIN_LIMIT') {
                        showToast(res.message);
                    }
                } catch (e) {}
                await loadConversations();
            } else if (action === 'delete') {
                openDeleteModal(c);
            }
        });
    });
    document.addEventListener('click', (e) => {
        if (!convMenu.hidden && !convMenu.contains(e.target)) closeConvMenu();
    });
    window.addEventListener('scroll', closeConvMenu, true);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !convMenu.hidden) closeConvMenu();
    });

    // ── Modal de confirmación de eliminación ──
    const deleteModal = $('#delete-modal');
    const deleteConv = $('#delete-conv');
    const deleteMeta = $('#delete-meta');
    const ES_MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
        'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    function formatEsDate(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        return `${d.getDate()} de ${ES_MONTHS[d.getMonth()]}`;
    }
    let deleteTargetId = null;
    function openDeleteModal(c) {
        if (!c) return;
        deleteTargetId = c.id;
        deleteConv.textContent = `“${c.title || 'Untitled analysis'}”`;
        const n = c.message_count || 0;
        deleteMeta.textContent = `Created ${formatEsDate(c.created_at)} • ${n} ${n === 1 ? 'message' : 'messages'}`;
        deleteModal.hidden = false;
        setTimeout(() => $('#delete-cancel').focus(), 30);
    }
    function closeDeleteModal() { deleteModal.hidden = true; deleteTargetId = null; }
    async function confirmDelete() {
        const cid = deleteTargetId;
        if (!cid) { closeDeleteModal(); return; }
        closeDeleteModal();
        const wasCurrent = cid === currentConvId;
        if (wasCurrent) {
            currentConvId = null;
            titleEl.textContent = 'New analysis';
            destroyChatCharts();
            messagesEl.innerHTML = '';
            showEmptyState();
            setMode('welcome');
        }
        const item = convListEl.querySelector(`.conv-item[data-cid="${cid}"]`);
        if (item) item.classList.add('removing');
        try {
            await apiDelete(`${API}/${cid}`);
        } catch (e) { /* silencioso */ }
        await loadConversations();
    }
    $('#delete-cancel').addEventListener('click', closeDeleteModal);
    $('#delete-confirm').addEventListener('click', confirmDelete);
    deleteModal.addEventListener('click', (e) => { if (e.target === deleteModal) closeDeleteModal(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !deleteModal.hidden) closeDeleteModal();
    });

    // ── Modal de contexto (copiar / editar / exportar) ──
    const contextModal = $('#context-modal');
    let contextCharts = [];
    function closeContextModal() { contextModal.hidden = true; }

    // Los botones del header (contexto / renombrar) solo tienen sentido si hay
    // una conversación activa Y esta ya contiene mensajes (un borrador vacío no
    // tiene contexto ni necesita renombrarse todavía).
    function updateHeaderButtons() {
        const show = !!(currentConvId && currentConvHasMessages);
        const ctx = $('#btn-context');
        if (ctx) ctx.style.display = show ? '' : 'none';
        const edit = $('#btn-edit-title');
        if (edit) edit.style.display = show ? '' : 'none';
    }

    function copyText(text) {
        const done = () => showToast('Copiado al portapapeles');
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text));
        } else {
            fallbackCopy(text);
        }
    }
    function fallbackCopy(text) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); showToast('Copiado al portapapeles'); } catch (e) { /* noop */ }
        document.body.removeChild(ta);
    }
    function buildTranscriptMd(messages, title) {
        let md = `# ${title || 'Copilot VZ Analysis'}\n\n`;
        (messages || []).forEach((m) => {
            const who = m.role === 'user' ? 'Tú' : 'Copilot VZ';
            md += `**${who}:**\n${m.content}\n\n`;
        });
        return md;
    }
    function downloadMd(title, text) {
        const safe = (title || 'analisis-copilot-vz')
            .replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 60)
            || 'analisis-copilot-vz';
        const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = safe + '.md';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    function renderContext(messages, title) {
        const body = $('#context-body');
        body.innerHTML = '';
        (messages || []).forEach((m) => {
            const isUser = m.role === 'user';
            const block = document.createElement('div');
            block.className = 'vz-ctx-msg' + (isUser ? ' user' : '');
            const role = isUser ? 'Tú' : 'Copilot VZ';
            const actions = '<button class="vz-ctx-act" data-act="copy">Copiar</button>';
            block.innerHTML =
                `<div class="vz-ctx-head">
                    <span class="vz-ctx-role ${isUser ? 'user' : 'assistant'}">${role}</span>
                    <div class="vz-ctx-actions">${actions}</div>
                </div>
                <div class="vz-ctx-text">${renderMarkdown(m.content)}</div>`;
            block.querySelector('[data-act="copy"]').onclick = () => copyText(m.content);
            body.appendChild(block);
        });
    }
    async function openContextModal() {
        if (!currentConvId) {
            showToast('Open or create a conversation to see its context');
            return;
        }
        try {
            const data = await apiGet(`${API}/${currentConvId}`);
            if (!data.success || !data.data) return;
            const conv = data.data;
            if (!conv.messages || !conv.messages.length) {
                showToast('No context yet in this conversation');
                return;
            }
            $('#context-sub').textContent = conv.title || 'Untitled analysis';
            renderContext(conv.messages || [], conv.title);
            // Reúne las gráficas de la conversación para el visor de exportación.
            contextCharts = (conv.messages || [])
                .filter((m) => m.metadata && m.metadata.chart)
                .map((m) => m.metadata.chart);
            $('#context-chart-btn').hidden = contextCharts.length === 0;
            contextModal.hidden = false;
        } catch (e) { /* silencioso */ }
    }
    $('#btn-context').addEventListener('click', openContextModal);
    $('#context-close').addEventListener('click', closeContextModal);
    contextModal.addEventListener('click', (e) => { if (e.target === contextModal) closeContextModal(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !contextModal.hidden) closeContextModal();
    });
    $('#context-copy-all').addEventListener('click', async () => {
        try {
            const data = await apiGet(`${API}/${currentConvId}`);
            if (data.success && data.data) copyText(buildTranscriptMd(data.data.messages, data.data.title));
        } catch (e) { /* silencioso */ }
    });
    $('#context-download').addEventListener('click', async () => {
        try {
            const data = await apiGet(`${API}/${currentConvId}`);
            if (data.success && data.data) {
                downloadMd(data.data.title, buildTranscriptMd(data.data.messages, data.data.title));
            }
        } catch (e) { /* silencioso */ }
    });

    // ── Visor de gráficas (exportar en tamaño grande) ──
    const chartModal = $('#chart-modal');
    let chartExportInstances = [];
    function renderChartExport(chartData, canvas) {
        // Reutiliza el mismo estilo profesional que el chat (sin título
        // duplicado: la tarjeta del visor ya muestra el título).
        return createChart(canvas, chartData, false, false);
    }
    function downloadChartPng(chart, title) {
        const url = chart.toBase64Image('image/png', 1);
        const safe = (title || 'grafica-copilot-vz')
            .replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 60)
            || 'grafica-copilot-vz';
        const a = document.createElement('a');
        a.href = url;
        a.download = safe + '.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
    function openChartModal() {
        const body = $('#chart-body');
        chartExportInstances.forEach((c) => { try { c.destroy(); } catch (e) { /* noop */ } });
        chartExportInstances = [];
        body.innerHTML = '';
        if (!contextCharts.length) {
            showToast('Esta conversación no tiene gráficas.');
            return;
        }
        contextCharts.forEach((chartData, idx) => {
            const title = chartData.title || `Gráfica ${idx + 1}`;
            const card = document.createElement('div');
            card.className = 'vz-chart-card';
            card.innerHTML =
                `<div class="vz-chart-card-head">
                    <span>${escapeHtml(title)}</span>
                    <button type="button" class="vz-ctx-act">Descargar PNG</button>
                </div>
                <div class="vz-chart-canvas-wrap"><canvas></canvas></div>`;
            body.appendChild(card);
            const canvas = card.querySelector('canvas');
            canvas.width = 900;
            canvas.height = 420;
            canvas.style.maxWidth = '100%';
            const inst = renderChartExport(chartData, canvas);
            chartExportInstances.push(inst);
            card.querySelector('.vz-ctx-act').onclick = () => downloadChartPng(inst, title);
        });
        chartModal.hidden = false;
    }
    function closeChartModal() {
        chartExportInstances.forEach((c) => { try { c.destroy(); } catch (e) { /* noop */ } });
        chartExportInstances = [];
        chartModal.hidden = true;
    }
    $('#context-chart-btn').addEventListener('click', () => {
        closeContextModal();
        openChartModal();
    });
    $('#chart-close').addEventListener('click', closeChartModal);
    chartModal.addEventListener('click', (e) => { if (e.target === chartModal) closeChartModal(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !chartModal.hidden) closeChartModal();
    });

    // ── Anillo de contexto ──
    function updateContextRing(pct) {
        let ctxWrap = document.getElementById('ctx-ring-wrap');
        if (pct == null || pct <= 0) {
            if (ctxWrap) ctxWrap.remove();
            return;
        }
        if (!ctxWrap) {
            ctxWrap = document.createElement('div');
            ctxWrap.id = 'ctx-ring-wrap';
            ctxWrap.className = 'flex items-center gap-1 shrink-0 self-center mb-0.5';
            ctxWrap.innerHTML =
                '<svg width="15" height="15" viewBox="0 0 18 18" class="shrink-0">' +
                '<circle cx="9" cy="9" r="7" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="2.5" />' +
                '<circle id="ctx-ring" cx="9" cy="9" r="7" fill="none" stroke="#10B981" ' +
                'stroke-width="2.5" stroke-linecap="round" stroke-dasharray="44" stroke-dashoffset="0" ' +
                'transform="rotate(-90,9,9)" /></svg>' +
                '<span id="ctx-pct" class="text-[11px] tabular-nums text-[var(--text-dim)]">0%</span>';
            const composer = document.querySelector('.vz-glass-composer');
            const sendBtn = document.getElementById('chat-send');
            if (composer && sendBtn) composer.insertBefore(ctxWrap, sendBtn);
        }
        const ctxRing = document.getElementById('ctx-ring');
        const ctxPct = document.getElementById('ctx-pct');
        const circ = 2 * Math.PI * 7;
        const offset = circ - (pct / 100) * circ;
        ctxRing.style.strokeDasharray = circ;
        ctxRing.style.strokeDashoffset = offset;
        ctxPct.textContent = pct + '%';
        ctxRing.style.stroke = pct < 60 ? '#10B981' : pct < 85 ? '#F59E0B' : '#EF4444';
    }
    updateContextRing(0);

    // ── Toast de aviso ──
    const toastEl = $('#vz-toast');
    let toastTimer = null;
    function showToast(msg) {
        toastEl.textContent = msg;
        toastEl.hidden = false;
        requestAnimationFrame(() => toastEl.classList.add('show'));
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toastEl.classList.remove('show');
            setTimeout(() => { toastEl.hidden = true; }, 220);
        }, 3200);
    }
    document.querySelectorAll('.sugg-chip').forEach((chip) => {
        chip.addEventListener('click', () => {
            inputEl.value = chip.textContent.trim();
            autoResize();
            inputEl.focus();
        });
    });
    // (vacio: quick-insights se renderiza dinámicamente desde JS)

    // ── Buscador de conversaciones ──
    const convSearchInput = $('#conv-search');
    if (convSearchInput) {
        convSearchInput.addEventListener('input', (e) => {
            convSearchTerm = e.target.value;
            renderConversations();
        });
    }

    // ── Init ───────────────────────────────────────────────
    // ── Onboarding: alta de categoría / producto / pedido ──────────────────
    const OB_BASE = '/insights/api/onboarding';
    let _onboardingCache = null;

    async function apiForm(url, form) {
        const r = await fetch(url, { method: 'POST', credentials: 'same-origin', body: form });
        return r.json();
    }

    async function fetchOnboarding(force) {
        if (!force && _onboardingCache) return _onboardingCache;
        try {
            const data = await apiGet(OB_BASE);
            if (data && data.success) { _onboardingCache = data; return data; }
        } catch (e) {}
        return null;
    }

    // Tras crear algo, refresca la guía de onboarding para que avance de nivel.
    async function refreshOnboardingCard() {
        const ob = await fetchOnboarding(true);
        const existing = document.getElementById('ob-card');
        if (!existing) return;
        if (ob && ob.card) {
            renderOnboardingCard(ob.card);
        } else {
            existing.remove();
            appendOnboardingDone();
        }
    }

    function onbModalEl(kind) { return document.getElementById('onb-' + kind + '-modal'); }

    function showOnbErr(kind, msg) {
        const el = document.getElementById('onb-' + kind + '-err');
        if (!el) return;
        el.textContent = msg;
        el.classList.remove('hidden');
    }
    function clearOnbErr(kind) {
        const el = document.getElementById('onb-' + kind + '-err');
        if (el) el.classList.add('hidden');
    }
    function setOnbSaving(kind, saving) {
        const btn = document.getElementById('onb-' + kind + '-save');
        if (btn) btn.disabled = saving;
    }

    // Si el usuario abrió el modal de categoría desde el de producto
    // (porque no tenía ninguna), tras crearla volvemos al de producto.
    let onbReturnToProduct = false;

    async function openOnbModal(kind) {
        const modal = onbModalEl(kind);
        if (!modal) return;
        modal.hidden = false;
        clearOnbErr(kind);
        if (kind === 'product') await loadOnbCategories();
        else if (kind === 'order') await loadOnbProducts();
    }

    function closeOnbModal(kind) {
        const modal = onbModalEl(kind);
        if (modal) modal.hidden = true;
        clearOnbErr(kind);
    }

    async function loadOnbCategories() {
        const sel = document.getElementById('onb-product-category');
        const note = document.getElementById('onb-product-nocat');
        const save = document.getElementById('onb-product-save');
        if (!sel) return;
        sel.classList.remove('hidden');
        if (note) note.classList.add('hidden');
        if (save) save.disabled = false;
        sel.innerHTML = '<option value="">Cargando…</option>';
        try {
            const data = await apiGet('/api/categories');
            const cats = (data && data.data && data.data.categories) || [];
            if (!cats.length) {
                sel.classList.add('hidden');
                if (note) note.classList.remove('hidden');
                if (save) save.disabled = true;
                return;
            }
            sel.innerHTML = cats.map((c) =>
                `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
        } catch (e) {
            sel.innerHTML = '<option value="">Error al cargar</option>';
        }
    }

    async function loadOnbProducts() {
        const sel = document.getElementById('onb-order-product');
        if (!sel) return;
        sel.innerHTML = '<option value="">Cargando…</option>';
        try {
            const data = await apiGet('/api/products?per_page=200');
            const prods = (data && data.data && data.data.products) || [];
            if (!prods.length) {
                sel.innerHTML = '<option value="">Sin productos aún</option>';
                return;
            }
            sel.innerHTML = prods.map((p) =>
                `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
        } catch (e) {
            sel.innerHTML = '<option value="">Error al cargar</option>';
        }
    }

    async function saveOnbCategory() {
        const nameEl = document.getElementById('onb-category-name');
        const name = (nameEl && nameEl.value || '').trim();
        if (!name) { showOnbErr('category', 'Ingresa un nombre para la categoría.'); return; }
        setOnbSaving('category', true);
        clearOnbErr('category');
        try {
            const fd = new FormData();
            fd.append('name', name);
            const data = await apiForm('/api/categories', fd);
            if (!data || !data.success) {
                showOnbErr('category', (data && data.error) || 'No se pudo crear la categoría.');
                return;
            }
            showToast('✓ Categoría creada');
            closeOnbModal('category');
            await refreshOnboardingCard();
            if (onbReturnToProduct) {
                onbReturnToProduct = false;
                openOnbModal('product'); // recarga las categorías automáticamente
            }
        } catch (e) {
            showOnbErr('category', 'Error de conexión.');
        } finally {
            setOnbSaving('category', false);
        }
    }

    async function saveOnbProduct() {
        const catEl = document.getElementById('onb-product-category');
        const nameEl = document.getElementById('onb-product-name');
        const priceEl = document.getElementById('onb-product-price');
        const catId = catEl && catEl.value;
        const name = (nameEl && nameEl.value || '').trim();
        const price = parseInt((priceEl && priceEl.value || '').trim(), 10);
        if (!catId) { showOnbErr('product', 'Primero elige o crea una categoría.'); return; }
        if (!name) { showOnbErr('product', 'Ingresa un nombre para el producto.'); return; }
        if (!Number.isFinite(price) || price < 1) {
            showOnbErr('product', 'El precio debe ser un número mayor a 0.'); return;
        }
        setOnbSaving('product', true);
        clearOnbErr('product');
        try {
            const fd = new FormData();
            fd.append('name', name);
            fd.append('price', String(price));
            fd.append('category_id', String(catId));
            const data = await apiForm('/api/products', fd);
            if (!data || !data.success) {
                showOnbErr('product', (data && data.error) || 'No se pudo crear el producto.');
                return;
            }
            showToast('✓ Producto creado');
            closeOnbModal('product');
            await refreshOnboardingCard();
        } catch (e) {
            showOnbErr('product', 'Error de conexión.');
        } finally {
            setOnbSaving('product', false);
        }
    }

    async function saveOnbOrder() {
        const prodEl = document.getElementById('onb-order-product');
        const qtyEl = document.getElementById('onb-order-qty');
        const prodId = prodEl && prodEl.value;
        const qty = parseInt((qtyEl && qtyEl.value || '').trim(), 10);
        if (!prodId) { showOnbErr('order', 'Primero crea un producto.'); return; }
        if (!Number.isFinite(qty) || qty < 1) {
            showOnbErr('order', 'La cantidad debe ser al menos 1.'); return;
        }
        setOnbSaving('order', true);
        clearOnbErr('order');
        try {
            const data = await apiSend('/api/orders', {
                customer_name: 'Cliente de prueba',
                items: [{ product_id: parseInt(prodId, 10), quantity: qty }],
            });
            if (!data || !data.success) {
                showOnbErr('order', (data && data.error) || 'No se pudo crear el pedido.');
                return;
            }
            showToast('✓ Venta de prueba registrada');
            closeOnbModal('order');
            await refreshOnboardingCard();
        } catch (e) {
            showOnbErr('order', 'Error de conexión.');
        } finally {
            setOnbSaving('order', false);
        }
    }

    (async function init() {
        await loadConversations();
        updateHeaderButtons();
        autoResize();

        // Onboarding: cierre, apertura cruzada y guardado.
        document.querySelectorAll('[data-onb-close]').forEach((b) => {
            b.addEventListener('click', () => closeOnbModal(b.dataset.onbClose));
        });
        document.querySelectorAll('[data-onb-open]').forEach((b) => {
            b.addEventListener('click', () => {
                if (b.closest('#onb-product-modal')) onbReturnToProduct = true;
                closeOnbModal('product');
                openOnbModal(b.dataset.onbOpen);
            });
        });
        ['category', 'product', 'order'].forEach((kind) => {
            const m = onbModalEl(kind);
            if (m) m.addEventListener('click', (e) => { if (e.target === m) closeOnbModal(kind); });
        });
        const cs = document.getElementById('onb-category-save'); if (cs) cs.addEventListener('click', saveOnbCategory);
        const ps = document.getElementById('onb-product-save'); if (ps) ps.addEventListener('click', saveOnbProduct);
        const os = document.getElementById('onb-order-save'); if (os) os.addEventListener('click', saveOnbOrder);

        // Prioridad: hash #conv=ID > última conversación guardada > bienvenida.
        var hashMatch = window.location.hash.match(/^#conv=(\d+)$/);
        if (hashMatch) {
            var convId = parseInt(hashMatch[1], 10);
            history.replaceState(null, '', window.location.pathname);
            await selectConversation(convId).catch(function (err) {
                console.warn('[Copilot VZ] init: hash conversation load failed', err);
                showEmptyState();
            });
        } else {
            var savedConvId = null;
            try { savedConvId = localStorage.getItem('vz_last_conv'); } catch (e) {}
            if (savedConvId) {
                var numId = parseInt(savedConvId, 10);
                if (!isNaN(numId) && numId > 0) {
                    await selectConversation(numId).catch(function (err) {
                        console.warn('[Copilot VZ] init: saved conversation load failed', err);
                        showEmptyState();
                    });
                } else {
                    showEmptyState();
                }
            } else {
                showEmptyState();
            }
        }
    })();

    /* ── Mobile keyboard: mantiene scroll visible al abrir/cerrar ── */
    (function attachKeyboardGuards() {
        var input = document.getElementById('chat-input');
        if (!input) return;

        function scrollBottom() {
            requestAnimationFrame(function () {
                scrollToBottom();
            });
        }

        input.addEventListener('focus', function () {
            setTimeout(scrollBottom, 100);
        });
        input.addEventListener('blur', function () {
            setTimeout(scrollBottom, 100);
        });

        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', function () {
                scrollBottom();
            }, { passive: true });
        }
    })();
})();

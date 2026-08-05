/**
 * cash-register-copilot.js — Widget de Copilot de Caja
 *
 * Drawer de chat flotante dentro del Centro de Caja (/cash-register).
 * Reutiliza los helpers globales de cash-register.js (crState, crRangeParams,
 * crCustomRangeComplete, crGetCSRF, formatCOP, escapeHtml) para anclar el
 * análisis al periodo activo de la pantalla.
 *
 * El drawer tiene dos vistas:
 *   - Lista de conversaciones (historial, abierta desde el botón historial
 *     del propio drawer).
 *   - Chat activo (conversación cargada con su historial de mensajes).
 *
 * Flujo: GET  /cash-register/copilot/conversations        → lista
 *        POST /cash-register/copilot/conversations        → crea
 *        GET  /cash-register/copilot/conversations/<id>   → historial
 *        POST /cash-register/copilot/conversations/<id>/messages → turno
 */

(function () {
    'use strict';

    const COPS = {
        newConversation: 'Analizando tu caja…',
        sending: 'Analizando tu caja…',
        noPeriod: 'Para analizar un rango personalizado primero selecciona las fechas en el selector y pulsa "Aplicar".',
        noCredits: 'No tienes tokens disponibles. Recarga tu plan para seguir analizando.',
        subscriptionRequired: 'Necesitas una suscripción activa para usar el análisis IA.',
        llmError: 'No pude completar el análisis. Intenta de nuevo en un momento.',
        genericError: 'Ocurrió un error. Intenta de nuevo.',
        emptyHistory: 'Todavía no tienes conversaciones. Crea una nueva para empezar.',
        retryChip: '¿Cuánto vendí hoy?',
        chips: ['¿Cuánto vendí hoy?', '¿Cómo le fue al efectivo?', '¿Cuánto falta por cobrar?'],
    };

    let crcState = {
        convId: null,
        busy: false,
        view: 'chat', // 'chat' | 'list'
        fab: null,
    };

    let fabLastScroll = 0;
    let fabHidden = false;

    /* ── DOM ────────────────────────────────────────────────────────────── */

    function buildWidget() {
        const root = document.createElement('div');
        root.id = 'crc-root';
        root.innerHTML = `
            <div id="crc-backdrop" class="crc-backdrop"></div>
            <aside id="crc-drawer" class="crc-drawer" role="dialog" aria-label="Copilot de Caja" aria-hidden="true">
                <div class="crc-header">
                    <div class="crc-header-icon">
                        <span class="material-symbols-outlined">account_balance_wallet</span>
                    </div>
                    <div class="crc-header-title">
                        <h3 id="crc-title">Copilot de Caja</h3>
                        <p id="crc-subtitle">Pregunta por tu dinero</p>
                    </div>
                    <button type="button" id="crc-history" class="crc-icon-btn" title="Historial de conversaciones" aria-label="Historial de conversaciones">
                        <span class="material-symbols-outlined">history</span>
                    </button>
                    <button type="button" id="crc-new" class="crc-icon-btn" title="Nueva conversación" aria-label="Nueva conversación">
                        <span class="material-symbols-outlined">add_comment</span>
                    </button>
                    <button type="button" id="crc-close" class="crc-icon-btn" title="Cerrar" aria-label="Cerrar">
                        <span class="material-symbols-outlined">close</span>
                    </button>
                </div>
                <div id="crc-list" class="crc-list" hidden></div>
                <div id="crc-messages" class="crc-messages"></div>
                <div id="crc-input-bar" class="crc-input-bar">
                    <textarea id="crc-input" class="crc-input" rows="1" placeholder="Pregunta por tu caja…"
                        aria-label="Mensaje para el Copilot de Caja"></textarea>
                    <button type="button" id="crc-send" class="crc-send" aria-label="Enviar mensaje">
                        <span class="material-symbols-outlined">arrow_upward</span>
                    </button>
                </div>
            </aside>
        `;
        document.body.appendChild(root);

        const fab = document.getElementById('crc-fab');
        if (fab) {
            crcState.fab = fab;
            fab.addEventListener('click', toggle);
            initFabScroll();
        }
        document.getElementById('crc-close').addEventListener('click', () => close());
        document.getElementById('crc-backdrop').addEventListener('click', () => close());
        document.getElementById('crc-new').addEventListener('click', () => startNew());
        document.getElementById('crc-history').addEventListener('click', toggleHistory);
        document.getElementById('crc-send').addEventListener('click', () => send());

        const input = document.getElementById('crc-input');
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
            }
        });
        input.addEventListener('input', () => autoGrow(input));
    }

    function el(id) {
        return document.getElementById(id);
    }

    /* ── FAB: ocultar al hacer scroll hacia abajo ───────────────────────── */

    function setFabHidden(hidden) {
        if (!crcState.fab) return;
        if (hidden) crcState.fab.classList.add('crc-fab-hide');
        else crcState.fab.classList.remove('crc-fab-hide');
        fabHidden = hidden;
    }

    function updateFab() {
        const y = window.scrollY || document.documentElement.scrollTop;
        const goingDown = y > fabLastScroll + 4;
        const goingUp = y < fabLastScroll - 4;
        fabLastScroll = y;

        // Al inicio de la página siempre visible; bajando se oculta; subiendo reaparece.
        if (y <= 80) {
            if (fabHidden) setFabHidden(false);
        } else if (goingDown && !fabHidden) {
            setFabHidden(true);
        } else if (goingUp && fabHidden) {
            setFabHidden(false);
        }
    }

    function initFabScroll() {
        let ticking = false;
        fabLastScroll = window.scrollY || 0;
        window.addEventListener('scroll', () => {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(() => {
                updateFab();
                ticking = false;
            });
        }, { passive: true });
    }

    function autoGrow(input) {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }

    function appendMsg(html, cls) {
        const m = el('crc-messages');
        const div = document.createElement('div');
        div.className = 'crc-msg ' + cls;
        div.innerHTML = html;
        m.appendChild(div);
        m.scrollTop = m.scrollHeight;
    }

    // Markdown mínimo y seguro: siempre escapa primero, luego aplica formato.
    function renderMarkdown(src) {
        let s = escapeHtml(src || '');
        s = s
            .replace(/^###\s+(.+)$/gm, '<h3 class="crc-md-h">$1</h3>')
            .replace(/^##\s+(.+)$/gm, '<h2 class="crc-md-h">$1</h2>')
            .replace(/^#\s+(.+)$/gm, '<h1 class="crc-md-h">$1</h1>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/__(.+?)__/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/_(.+?)_/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code class="crc-md-code">$1</code>')
            .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
                '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
            .replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>')
            .replace(/(<li>[\s\S]*?<\/li>)(?:\s*<li>[\s\S]*?<\/li>)*/g,
                (m) => '<ul class="crc-md-ul">' + m + '</ul>')
            .replace(/\n/g, '<br>');
        return s;
    }

    function appendTyping() {
        const m = el('crc-messages');
        const div = document.createElement('div');
        div.className = 'crc-msg crc-msg-assistant crc-msg-typing';
        div.id = 'crc-typing';
        div.innerHTML = '<span></span><span></span><span></span>';
        m.appendChild(div);
        m.scrollTop = m.scrollHeight;
    }

    function removeTyping() {
        const t = el('crc-typing');
        if (t) t.remove();
    }

    function setBusy(b) {
        crcState.busy = b;
        el('crc-send').disabled = b;
        el('crc-input').disabled = b;
    }

    /* ── Apertura / cierre ─────────────────────────────────────────────── */

    function openChat() {
        showChat();
        openDrawer();
        if (!crcState.convId && !crcState.busy) ensureConversation();
        setTimeout(() => el('crc-input').focus(), 150);
    }

    function openDrawer() {
        el('crc-drawer').classList.add('open');
        el('crc-drawer').setAttribute('aria-hidden', 'false');
        el('crc-backdrop').classList.add('open');
        document.body.style.overflow = 'hidden';
        setFabHidden(true);
    }

    function close() {
        el('crc-drawer').classList.remove('open');
        el('crc-drawer').setAttribute('aria-hidden', 'true');
        el('crc-backdrop').classList.remove('open');
        document.body.style.overflow = '';
        // Re-evalúa el FAB según la posición actual del scroll al cerrar el chat.
        fabLastScroll = window.scrollY || 0;
        setFabHidden(false);
    }

    function toggle() {
        if (el('crc-drawer').classList.contains('open')) close();
        else openChat();
    }

    /* ── Vistas: chat ↔ lista de conversaciones ────────────────────────── */

    function showChat() {
        crcState.view = 'chat';
        el('crc-list').hidden = true;
        el('crc-messages').hidden = false;
        el('crc-input-bar') && (el('crc-input-bar').hidden = false);
        el('crc-history').title = 'Historial de conversaciones';
        el('crc-history').setAttribute('aria-label', 'Historial de conversaciones');
        el('crc-history').querySelector('span').textContent = 'history';
        el('crc-title').textContent = 'Copilot de Caja';
        el('crc-subtitle').textContent = 'Pregunta por tu dinero';
        el('crc-new').title = 'Nueva conversación';
        el('crc-new').setAttribute('aria-label', 'Nueva conversación');
        el('crc-new').querySelector('span').textContent = 'add_comment';
    }

    function showList() {
        crcState.view = 'list';
        el('crc-list').hidden = false;
        el('crc-messages').hidden = true;
        el('crc-input-bar') && (el('crc-input-bar').hidden = true);
        el('crc-history').title = 'Volver al chat';
        el('crc-history').setAttribute('aria-label', 'Volver al chat');
        el('crc-history').querySelector('span').textContent = 'chat_bubble';
        el('crc-title').textContent = 'Conversaciones';
        el('crc-subtitle').textContent = 'Historial de chats';
        el('crc-new').title = 'Nuevo chat';
        el('crc-new').setAttribute('aria-label', 'Nuevo chat');
        el('crc-new').querySelector('span').textContent = 'add';
        loadList();
    }

    function toggleHistory() {
        if (crcState.busy) return;
        if (crcState.view === 'list') {
            if (crcState.convId) openConversation(crcState.convId);
            else openChat();
        } else {
            showList();
        }
    }

    async function loadList() {
        const listEl = el('crc-list');
        listEl.innerHTML = `
            <div class="crc-list-loading">
                <span class="crc-spinner"></span>
            </div>
        `;
        try {
            const res = await fetch('/cash-register/copilot/conversations');
            const body = await res.json().catch(() => ({}));
            const convs = (body && body.data) || [];
            if (!convs.length) {
                listEl.innerHTML = `
                    <div class="crc-list-empty">
                        <span class="material-symbols-outlined">chat_bubble_outline</span>
                        <p>${escapeHtml(COPS.emptyHistory)}</p>
                        <button type="button" class="crc-list-new" id="crc-list-new-empty">Nuevo chat</button>
                    </div>
                `;
                const n = document.getElementById('crc-list-new-empty');
                if (n) n.addEventListener('click', () => startNew());
                return;
            }
            listEl.innerHTML = convs.map((c) => `
                <button type="button" class="crc-list-item" data-id="${c.id}">
                    <span class="material-symbols-outlined crc-list-item-icon">chat_bubble_outline</span>
                    <span class="crc-list-item-title">${escapeHtml(c.title || 'Análisis de caja')}</span>
                    ${c.analysis_active ? '<span class="crc-list-item-dot" title="Análisis en curso"></span>' : ''}
                </button>
            `).join('');
            listEl.querySelectorAll('.crc-list-item').forEach((item) => {
                item.addEventListener('click', () => openConversation(Number(item.dataset.id)));
            });
        } catch (e) {
            listEl.innerHTML = `<div class="crc-list-empty"><p>${escapeHtml(COPS.genericError)}</p></div>`;
        }
    }

    async function openConversation(cid) {
        if (crcState.busy) return;
        crcState.convId = cid;
        showChat();
        el('crc-messages').innerHTML = '';
        setBusy(true);
        appendTyping();
        try {
            const res = await fetch(`/cash-register/copilot/conversations/${cid}`);
            const body = await res.json().catch(() => ({}));
            const data = body && body.data;
            removeTyping();
            if (!res.ok || !data) {
                crcState.convId = null;
                showWelcome();
                return;
            }
            const messages = data.messages || [];
            if (!messages.length) {
                showWelcome();
                return;
            }
            messages.forEach((m) => {
                if (m.role === 'user') {
                    appendMsg(escapeHtml(m.content || ''), 'crc-msg-user');
                } else if (m.role === 'assistant') {
                    let html = renderMarkdown(m.content || '');
                    const meta = m.metadata || null;
                    if (meta && meta.chart) html += renderChart(meta.chart);
                    appendMsg(html, 'crc-msg-assistant');
                }
            });
        } catch (e) {
            removeTyping();
            crcState.convId = null;
            showWelcome();
        } finally {
            setBusy(false);
        }
    }

    async function ensureConversation() {
        if (crcState.busy) return;
        setBusy(true);
        try {
            const res = await fetch('/cash-register/copilot/conversations');
            const body = await res.json().catch(() => ({}));
            const list = (body && body.data) || [];
            if (list.length) {
                crcState.convId = list[0].id;
                setBusy(false);
                await openConversation(crcState.convId);
            } else {
                const created = await fetch('/cash-register/copilot/conversations', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': crGetCSRF(),
                    },
                    body: JSON.stringify({}),
                });
                const cb = await created.json().catch(() => ({}));
                crcState.convId = cb.data ? cb.data.id : null;
                showWelcome();
            }
        } catch (e) {
            appendMsg(escapeHtml(COPS.genericError), 'crc-msg-system');
        } finally {
            setBusy(false);
        }
    }

    function showWelcome() {
        el('crc-messages').innerHTML = `
            <div class="crc-welcome">
                <span class="material-symbols-outlined">account_balance_wallet</span>
                <h4>¿Qué necesitas revisar hoy?</h4>
                <p>Estoy aquí para ayudarte a encontrar ventas, consultar pagos, revisar pedidos pendientes o responder dudas sobre tu caja.</p>
                <div class="crc-chips">
                    ${COPS.chips.map((c) => `<button type="button" class="crc-chip">${escapeHtml(c)}</button>`).join('')}
                </div>
            </div>
        `;
        el('crc-messages').querySelectorAll('.crc-chip').forEach((chip) => {
            chip.addEventListener('click', () => {
                el('crc-input').value = chip.textContent;
                send();
            });
        });
    }

    async function startNew() {
        if (crcState.busy) return;
        setBusy(true);
        crcState.convId = null;
        el('crc-messages').innerHTML = '';
        showChat();
        try {
            const created = await fetch('/cash-register/copilot/conversations', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': crGetCSRF(),
                },
                body: JSON.stringify({}),
            });
            const cb = await created.json().catch(() => ({}));
            crcState.convId = cb.data ? cb.data.id : null;
            showWelcome();
        } catch (e) {
            appendMsg(escapeHtml(COPS.genericError), 'crc-msg-system');
        } finally {
            setBusy(false);
            el('crc-input').focus();
        }
    }

    /* ── Envío de mensaje ──────────────────────────────────────────────── */

    function activePeriod() {
        const p = { range: crState.range };
        if (crState.range === 'custom') {
            p.from = crState.customFrom;
            p.to = crState.customTo;
        }
        return p;
    }

    function send() {
        if (crcState.busy) return;
        const input = el('crc-input');
        const content = input.value.trim();
        if (!content) return;

        if (crState.range === 'custom' && !crCustomRangeComplete()) {
            appendMsg(escapeHtml(COPS.noPeriod), 'crc-msg-system');
            return;
        }
        if (!crcState.convId) {
            appendMsg(escapeHtml(COPS.newConversation), 'crc-msg-system');
            ensureConversation().then(() => sendQueued(content));
            return;
        }
        sendQueued(content);
    }

    async function sendQueued(content) {
        if (!crcState.convId) return;
        const input = el('crc-input');
        input.value = '';
        autoGrow(input);
        setBusy(true);
        appendMsg(escapeHtml(content), 'crc-msg-user');
        appendTyping();

        try {
            const res = await fetch(`/cash-register/copilot/conversations/${crcState.convId}/messages`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': crGetCSRF(),
                },
                body: JSON.stringify({
                    content: content,
                    period: activePeriod(),
                }),
            });
            const body = await res.json().catch(() => ({}));

            removeTyping();

            if (!res.ok || !body.success) {
                appendMsg(escapeHtml(body.error || COPS.genericError), 'crc-msg-system');
                return;
            }

            if (body.type === 'no_credits') {
                appendMsg(escapeHtml(COPS.noCredits), 'crc-msg-system');
                return;
            }
            if (body.type === 'subscription_required') {
                appendMsg(escapeHtml(COPS.subscriptionRequired), 'crc-msg-system');
                return;
            }
            if (body.type === 'llm_error' || body.type === 'error') {
                appendMsg(escapeHtml(body.message || COPS.llmError), 'crc-msg-system');
                return;
            }

            let html = renderMarkdown(body.content || '');
            if (body.chart) html += renderChart(body.chart);
            appendMsg(html, 'crc-msg-assistant');
        } catch (e) {
            removeTyping();
            appendMsg(escapeHtml(COPS.genericError), 'crc-msg-system');
        } finally {
            setBusy(false);
            el('crc-input').focus();
        }
    }

    /* ── Gráfica mínima (barras) ───────────────────────────────────────── */

    function renderChart(chart) {
        if (!chart || !chart.labels || !chart.datasets || !chart.datasets.length) return '';
        const ds = chart.datasets[0];
        const data = ds.data || [];
        if (!data.length) return '';
        const max = Math.max(...data.map(Number), 1);
        const rows = chart.labels.map((label, i) => {
            const v = Number(data[i] || 0);
            const pct = Math.max(2, Math.round((v / max) * 100));
            return `
                <div class="crc-chart-row">
                    <span class="crc-chart-label">${escapeHtml(label)}</span>
                    <span class="crc-chart-bar-wrap">
                        <span class="crc-chart-bar" style="width:${pct}%"></span>
                    </span>
                    <span class="crc-chart-val">${formatCOP(v)}</span>
                </div>
            `;
        }).join('');
        return `
            <div class="crc-chart">
                <div class="crc-chart-title">${escapeHtml(chart.title || 'Gráfica')}</div>
                ${rows}
            </div>
        `;
    }

    /* ── Init ──────────────────────────────────────────────────────────── */

    document.addEventListener('DOMContentLoaded', () => {
        buildWidget();
    });
})();

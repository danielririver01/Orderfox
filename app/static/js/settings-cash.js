/**
 * settings-cash.js — Ajustes → Caja (/dashboard/settings/caja)
 *
 * Configuración de caja registradora movida desde el Centro de Caja:
 * - Control de caja (require_cash_shift): exige turno abierto + conteo físico.
 * - Cajón físico QZ Tray (drawer_enabled / drawer_auto_open).
 *
 * Consume los mismos endpoints que usaba el Centro de Caja:
 * GET/PUT /cash-register/api/settings (solo dueño).
 */

const scState = {
    cashStrict: false,    // require_cash_shift
    drawerEnabled: false, // drawer_enabled
    drawerAuto: false,    // drawer_auto_open
    drawerInFlight: false,
};

const scEl = (id) => document.getElementById(id);

function scGetCSRF() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function scTogglePaint(btn, on, onLabel, offLabel) {
    btn.textContent = on ? onLabel : offLabel;
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.className = 'flex-shrink-0 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 border ' +
        (on
            ? 'bg-emerald-600 text-white border-emerald-600 shadow-lg shadow-emerald-500/20'
            : 'bg-white dark:bg-white/[0.05] text-gray-500 dark:text-gray-300 border-gray-200 dark:border-white/[0.08] hover:bg-gray-100 dark:hover:bg-white/[0.1]');
}

function scShowError(msg) {
    const err = scEl('cash-config-error');
    if (!err) return;
    if (msg) {
        err.textContent = msg;
        err.classList.remove('hidden');
    } else {
        err.classList.add('hidden');
    }
}

async function loadCashConfig() {
    try {
        const res = await fetch('/cash-register/api/settings');
        if (!res.ok) return; // no dueño: no debería llegar aquí (ruta owner-only)
        const body = await res.json();
        if (!body.success) return;
        scState.cashStrict = !!body.data.require_cash_shift;
        scState.drawerEnabled = !!body.data.drawer_enabled;
        scState.drawerAuto = !!body.data.drawer_auto_open;
        renderCashConfig();
        renderDrawerCard();
        if (typeof Drawer !== 'undefined') Drawer.renderStatus('drawer-status');
    } catch (err) {
        console.error('loadCashConfig:', err);
    }
}

function renderCashConfig() {
    const toggle = scEl('cash-config-toggle');
    if (!toggle) return;
    scTogglePaint(toggle, scState.cashStrict, 'Activado', 'Desactivado');
}

function renderDrawerCard() {
    const toggle = scEl('drawer-toggle');
    const autoToggle = scEl('drawer-auto-toggle');
    const autoRow = scEl('drawer-auto-row');
    if (!toggle || !autoToggle || !autoRow) return;
    scTogglePaint(toggle, scState.drawerEnabled, 'Activado', 'Desactivado');
    autoRow.classList.toggle('hidden', !scState.drawerEnabled);
    autoRow.classList.toggle('flex', !!scState.drawerEnabled);
    scTogglePaint(autoToggle, scState.drawerAuto, 'Sí', 'No');
}

async function putCashSettings(payload) {
    const res = await fetch('/cash-register/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': scGetCSRF() },
        body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.success) throw new Error(body.error || 'No se pudo guardar');
    scState.cashStrict = !!body.data.require_cash_shift;
    scState.drawerEnabled = !!body.data.drawer_enabled;
    scState.drawerAuto = !!body.data.drawer_auto_open;
    renderCashConfig();
    renderDrawerCard();
}

async function toggleCashStrict() {
    const toggle = scEl('cash-config-toggle');
    scShowError('');
    toggle.disabled = true;
    try {
        await putCashSettings({ require_cash_shift: !scState.cashStrict });
    } catch (err) {
        console.error('toggleCashStrict:', err);
        scShowError('No se pudo guardar el control de caja. Inténtalo de nuevo.');
    } finally {
        toggle.disabled = false;
    }
}

async function toggleDrawerEnabled() {
    const btn = scEl('drawer-toggle');
    btn.disabled = true;
    try {
        await putCashSettings({ drawer_enabled: !scState.drawerEnabled });
        if (typeof Drawer !== 'undefined') Drawer.renderStatus('drawer-status');
    } catch (err) {
        console.error('toggleDrawerEnabled:', err);
    } finally {
        btn.disabled = false;
    }
}

async function toggleDrawerAuto() {
    const btn = scEl('drawer-auto-toggle');
    btn.disabled = true;
    try {
        await putCashSettings({ drawer_auto_open: !scState.drawerAuto });
    } catch (err) {
        console.error('toggleDrawerAuto:', err);
    } finally {
        btn.disabled = false;
    }
}

async function testDrawer() {
    if (scState.drawerInFlight || typeof Drawer === 'undefined') return;
    const btn = scEl('drawer-test-btn');
    const result = scEl('drawer-test-result');
    result.classList.add('hidden');
    scState.drawerInFlight = true;
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
        scState.drawerInFlight = false;
        btn.disabled = false;
        btn.textContent = 'Probar cajón';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCashConfig();
});

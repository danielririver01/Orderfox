/**
 * drawer.js — Cajón monedero físico vía QZ Tray (puente local).
 *
 * Cómo funciona:
 * - El cajón se conecta por RJ11 a la impresora de recibos (puerto DK).
 * - QZ Tray (instalado en el PC del mostrador) recibe la orden del navegador
 *   y manda el pulso ESC/POS `ESC p` a la impresora, que abre el cajón.
 * - Sin QZ instalado, o con el cajón desactivado en settings, todo el flujo
 *   de cobro funciona igual que siempre: este módulo NUNCA rompe un pago.
 *
 * API: Drawer.getConfig() | Drawer.getStatus() | Drawer.kick() |
 *      Drawer.autoKick(method) | Drawer.renderStatus(el)
 */

const Drawer = (() => {
    // Pulso estándar ESC/POS para cajón en pin 2 del puerto DK:
    // ESC p m t1 t2  →  1B 70 00 19 FA (t1=25, t2=250).
    // Si un cajón no abre con esto, probar pin 1: 1B 70 01 19 FA.
    const KICK_COMMAND = '\x1B' + '\x70' + '\x00' + '\x19' + '\xFA';

    const CONFIG_TTL_MS = 60000;
    let configCache = { at: 0, enabled: false, auto: false };

    async function getConfig() {
        const now = Date.now();
        if (now - configCache.at < CONFIG_TTL_MS) return configCache;
        try {
            const res = await fetch('/cash-register/api/drawer');
            if (!res.ok) return configCache; // 401/403 → se trata como desactivado
            const body = await res.json();
            if (body && body.success) {
                configCache = {
                    at: now,
                    enabled: !!body.data.drawer_enabled,
                    auto: !!body.data.drawer_auto_open,
                };
            }
        } catch (e) {
            /* sin red: se mantiene el último valor conocido */
        }
        return configCache;
    }

    function qzPresent() {
        return typeof qz !== 'undefined' && !!qz.websocket;
    }

    async function ensureConnected() {
        if (!qzPresent()) {
            throw new Error('qz-missing');
        }
        if (!qz.websocket.isActive()) {
            await qz.websocket.connect();
        }
    }

    /**
     * Manda el pulso de apertura. Resuelve true/false, NUNCA rechaza:
     * un fallo de hardware jamás debe tumbar el cobro.
     */
    async function kick() {
        try {
            await ensureConnected();
            const printer = await qz.printers.getDefault();
            if (!printer) return false;
            const config = qz.configs.create(printer);
            await qz.print(config, [KICK_COMMAND]);
            return true;
        } catch (e) {
            console.warn('Drawer.kick:', e && e.message ? e.message : e);
            return false;
        }
    }

    /**
     * Disparo automático tras un cobro. Fire-and-forget a propósito:
     * retorna de inmediato para no retrasar el flujo de caja.
     */
    function autoKick(method) {
        if (method !== 'cash') return;
        getConfig().then((cfg) => {
            if (cfg.enabled && cfg.auto) {
                kick();
            }
        }).catch(() => { /* nunca bloquear */ });
    }

    /**
     * Estado para la tarjeta de config: 'disabled' | 'no-qz' |
     * 'offline' | 'ready'.
     */
    async function getStatus() {
        const cfg = await getConfig();
        if (!cfg.enabled) return 'disabled';
        if (!qzPresent()) return 'no-qz';
        try {
            if (qz.websocket.isActive()) return 'ready';
            await qz.websocket.connect();
            return 'ready';
        } catch (e) {
            return 'offline';
        }
    }

    const STATUS_TEXT = {
        'disabled': ['Cajón desactivado', 'text-gray-500'],
        'detecting': ['Detectando QZ Tray…', 'text-gray-500'],
        'no-qz': ['QZ no detectado en este PC — instálalo para usar el cajón (qz.io/download)', 'text-amber-400'],
        'offline': ['QZ instalado pero apagado — ábrelo desde la bandeja del sistema y acepta el certificado', 'text-amber-400'],
        'ready': ['Listo: cajón conectado vía QZ Tray', 'text-emerald-400'],
    };

    async function renderStatus(el) {
        const target = typeof el === 'string' ? document.getElementById(el) : el;
        if (!target) return 'unknown';
        const paint = (key) => {
            const [text, cls] = STATUS_TEXT[key] || STATUS_TEXT['detecting'];
            target.className = 'text-[11px] font-bold ' + cls;
            target.textContent = text;
        };
        paint('detecting');
        const status = await getStatus();
        paint(status);
        return status;
    }

    return { getConfig, getStatus, kick, autoKick, renderStatus };
})();

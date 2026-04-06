/**
 * orders-realtime.js
 * Sistema de polling para detectar nuevos pedidos en tiempo real (cada 15s).
 * Muestra un Toast con botón AJAX para actualizar la lista SIN recargar la página.
 */

// ─── Estado del módulo ───────────────────────────────────────────────────────
let currentLastId = typeof LAST_ORDER_ID !== 'undefined' ? LAST_ORDER_ID : 0;
let soundEnabled = false;         // Off por defecto (user gesture requerido)
let audioCtx = null;              // Web Audio API context (lazy init)
let pollingInterval = null;
let newOrdersToastVisible = false;

// ─── Inicialización ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    restoreSoundPreference();
    startPolling();

    // Cualquier clic en la página habilita el contexto de audio si el sonido está activo
    document.addEventListener('click', unlockAudio, { once: true });
});

// ─── Polling ─────────────────────────────────────────────────────────────────
function startPolling() {
    pollingInterval = setInterval(checkForNewOrders, 15000); // 15 segundos
}

async function checkForNewOrders() {
    try {
        const res = await fetch('/dashboard/api/check-orders');
        if (!res.ok) return;

        const data = await res.json();

        if (data.last_id > currentLastId) {
            // ¡Nuevo/s pedido/s detectado/s!
            currentLastId = data.last_id;
            const count = data.pending_count;

            showNewOrdersToast(count);

            if (soundEnabled) {
                playNotificationSound();
            }

            // Actualizar el puntito del nav badge
            updateNavBadge(count);
        }
    } catch (err) {
        // Fallo silencioso — no interrumpir al usuario
        console.warn('[Velzia] Error en polling de pedidos:', err);
    }
}

// ─── AJAX Refresh (fragmento) ─────────────────────────────────────────────────
async function refreshOrderList() {
    dismissNewOrdersToast();

    const container = document.getElementById('orders-container');
    if (!container) { location.reload(); return; }

    // Animación de carga sutil
    container.style.opacity = '0.5';
    container.style.transition = 'opacity 0.2s ease';

    try {
        const res = await fetch('/orders/fragment');
        if (!res.ok) throw new Error('Fragment fetch failed');

        const html = await res.text();

        container.innerHTML = html;
        container.style.opacity = '1';

        // Actualizar contador del header
        const countEl = document.getElementById('orders-count');
        if (countEl) {
            const cards = container.querySelectorAll('[data-order-id]').length;
            countEl.textContent = `${cards} pedidos`;
        }

        showToast('✅ Pedidos actualizados', 'success');
    } catch (err) {
        container.style.opacity = '1';
        // Fallback: recarga completa si AJAX falla
        location.reload();
    }
}

// ─── Toast de nuevos pedidos ──────────────────────────────────────────────────
function showNewOrdersToast(pendingCount) {
    if (newOrdersToastVisible) return; // No acumular toasts

    const toast = document.getElementById('new-orders-toast');
    const msg = document.getElementById('new-orders-toast-msg');

    if (!toast || !msg) return;

    msg.textContent = pendingCount > 1
        ? `¡${pendingCount} pedidos pendientes!`
        : '¡Nuevo pedido entrando!';

    toast.classList.remove('hidden');
    newOrdersToastVisible = true;
}

function dismissNewOrdersToast() {
    const toast = document.getElementById('new-orders-toast');
    if (toast) toast.classList.add('hidden');
    newOrdersToastVisible = false;
}

// ─── Nav Badge (puntito naranja en icono de Pedidos) ─────────────────────────
function updateNavBadge(count) {
    const badge = document.getElementById('orders-nav-badge');
    if (!badge) return;
    if (count > 0) {
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

// ─── Sonido de notificación (Web Audio API — sin archivos externos) ───────────
function unlockAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

function playNotificationSound() {
    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }

        const t = audioCtx.currentTime;

        // Tono 1: frecuencia alta (ding!)
        const osc1 = audioCtx.createOscillator();
        const gain1 = audioCtx.createGain();
        osc1.connect(gain1);
        gain1.connect(audioCtx.destination);
        osc1.frequency.setValueAtTime(880, t);
        osc1.frequency.exponentialRampToValueAtTime(660, t + 0.15);
        gain1.gain.setValueAtTime(0.4, t);
        gain1.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
        osc1.start(t);
        osc1.stop(t + 0.4);

        // Tono 2: ligeramente después (doble ding suave)
        const osc2 = audioCtx.createOscillator();
        const gain2 = audioCtx.createGain();
        osc2.connect(gain2);
        gain2.connect(audioCtx.destination);
        osc2.frequency.setValueAtTime(1046, t + 0.18);
        osc2.frequency.exponentialRampToValueAtTime(784, t + 0.35);
        gain2.gain.setValueAtTime(0.3, t + 0.18);
        gain2.gain.exponentialRampToValueAtTime(0.001, t + 0.55);
        osc2.start(t + 0.18);
        osc2.stop(t + 0.55);

    } catch (err) {
        console.warn('[Velzia] No se pudo reproducir sonido:', err);
    }
}

// ─── Toggle de sonido ─────────────────────────────────────────────────────────
function toggleSound() {
    soundEnabled = !soundEnabled;
    localStorage.setItem('velzia_sound_enabled', soundEnabled ? '1' : '0');

    const icon = document.getElementById('sound-icon');
    const btn = document.getElementById('sound-toggle-btn');

    if (soundEnabled) {
        // Desbloquear contexto de audio con este gesto del usuario
        unlockAudio();

        icon.textContent = 'notifications_active';
        btn.classList.add('bg-orange-100', 'dark:bg-orange-500/10', 'text-orange-500');
        btn.classList.remove('text-gray-400', 'dark:text-gray-500');

        // Reproducir sonido de confirmación
        playNotificationSound();
        showToast('🔔 Alertas sonoras activadas', 'success');
    } else {
        icon.textContent = 'notifications_off';
        btn.classList.remove('bg-orange-100', 'dark:bg-orange-500/10', 'text-orange-500');
        btn.classList.add('text-gray-400', 'dark:text-gray-500');
        showToast('🔕 Alertas sonoras desactivadas', 'default');
    }
}

function restoreSoundPreference() {
    const saved = localStorage.getItem('velzia_sound_enabled');
    if (saved === '1') {
        // Restaurar estado visual sin reproducir sonido
        soundEnabled = true;
        const icon = document.getElementById('sound-icon');
        const btn = document.getElementById('sound-toggle-btn');
        if (icon) icon.textContent = 'notifications_active';
        if (btn) {
            btn.classList.add('bg-orange-100', 'text-orange-500');
            btn.classList.remove('text-gray-400', 'dark:text-gray-500');
        }
    }
}

// showToast ya viene de orders.js — se reutiliza aquí también.

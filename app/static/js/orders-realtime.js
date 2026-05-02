/**
 * orders-realtime.js
 * Sistema de polling para detectar nuevos pedidos en tiempo real (cada 15s).
 * Soporta Notificaciones de Sistema (Browser API) y sonidos.
 */

// ─── Estado del módulo ───────────────────────────────────────────────────────
let currentLastId = typeof LAST_ORDER_ID !== 'undefined' ? LAST_ORDER_ID : 0;
let soundEnabled = false;         // Controla sonido Y notificaciones de sistema
let audioCtx = null;              // Web Audio API context (lazy init)
let pollingInterval = null;
let newOrdersToastVisible = false;
let isFirstPoll = true;           // Para evitar notificar pedidos antiguos al cargar

// Canal de comunicación entre pestañas para evitar duplicados
const syncChannel = 'serviceWorker' in navigator ? new BroadcastChannel('velzia_orders_sync') : null;
if (syncChannel) {
    syncChannel.onmessage = (event) => {
        if (event.data && event.data.last_id > currentLastId) {
            currentLastId = event.data.last_id;
            // Si otra pestaña ya lo vio, nosotros no notificamos
            dismissNewOrdersToast();
        }
    };
}

// ─── Inicialización ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    restoreSoundPreference();
    startPolling();
    registerServiceWorker();

    // Cualquier clic en la página habilita el contexto de audio si el sonido está activo
    document.addEventListener('click', unlockAudio, { once: true });
});

async function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        try {
            const registration = await navigator.serviceWorker.register('/static/js/sw.js');

            // Escuchar mensajes del Service Worker
            navigator.serviceWorker.addEventListener('message', (event) => {
                if (event.data && event.data.action === 'REFRESH_ORDERS') {
                    if (typeof refreshOrderList === 'function') {
                        refreshOrderList();
                    } else {
                        window.location.reload();
                    }
                }
            });
        } catch (e) {
            console.warn('[Velzia] Error al registrar SW:', e);
        }
    }
}



// ─── Polling ─────────────────────────────────────────────────────────────────
function startPolling() {
    // Si ya hay un intervalo, lo limpiamos para evitar duplicados
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(checkForNewOrders, 10000); // 10 segundos (más rápido)
}


async function checkForNewOrders() {
    try {
        const res = await fetch('/dashboard/api/check-orders');
        if (!res.ok) return;

        const data = await res.json();

        // Inicialización del ID en la primera carga si no fue inyectado por el template
        if (isFirstPoll) {
            if (currentLastId === 0) {
                currentLastId = data.last_id;
            }
            isFirstPoll = false;
            return; // No notificar en el primer check (es el estado actual)
        }

        if (data.last_id > currentLastId) {
            // ¡Nuevo/s pedido/s detectado/s!
            currentLastId = data.last_id;
            const count = data.pending_count;

            // Avisar a otras pestañas que ya procesamos este ID
            if (syncChannel) {
                syncChannel.postMessage({ last_id: currentLastId });
            }

            // 1. Mostrar Toast si el elemento existe (en pantalla de pedidos)
            showNewOrdersToast(count);

            // 2. Notificación de sistema (Browser API)
            if (soundEnabled) {
                playNotificationSound();
                showBrowserNotification(count);
            }

            // 3. Actualizar el puntito del nav badge (global)
            updateNavBadge(count);
        }

    } catch (err) {
        console.warn('[Velzia] Error en polling de pedidos:', err);
    }
}

// ─── Notificaciones de Navegador ──────────────────────────────────────────────
async function showBrowserNotification(count) {
    if (!("Notification" in window)) return;

    if (Notification.permission === "granted") {
        const title = count > 1 ? `¡${count} pedidos pendientes!` : '¡Nuevo pedido entrante!';
        const options = {
            body: 'Revisa tu panel de administración para gestionar los pedidos actuales.',
            icon: '/static/img/icon-192x192.png',
            badge: '/static/img/badge-icon.png', // Icono pequeño para la barra de estado
            tag: 'new-order',
            renotify: true,
            silent: false, // Intentar que el sistema haga ruido
            vibrate: [200, 100, 200] // Vibración en móviles
        };


        // Intentar usar Service Worker si está disponible (mejor para segundo plano)
        const registration = await navigator.serviceWorker.ready;
        if (registration && registration.showNotification) {
            registration.showNotification(title, options);
        } else {
            // Fallback a notificación normal
            new Notification(title, options);
        }
    } else if (Notification.permission !== "denied") {
        // Si no tenemos permiso, lo pedimos de nuevo (esto puede ser intrusivo, pero el usuario lo pidió)
        requestNotificationPermission();
    }
}


async function requestNotificationPermission() {
    if (!("Notification" in window)) return false;

    if (Notification.permission !== "granted" && Notification.permission !== "denied") {
        const permission = await Notification.requestPermission();
        return permission === "granted";
    }
    return Notification.permission === "granted";
}

// ─── AJAX Refresh (fragmento) ─────────────────────────────────────────────────
async function refreshOrderList() {
    dismissNewOrdersToast();

    const container = document.getElementById('orders-container');
    if (!container) {
        // Si no estamos en la pantalla de pedidos, redirigimos
        window.location.href = '/orders/';
        return;
    }

    container.style.opacity = '0.5';
    container.style.transition = 'opacity 0.2s ease';

    try {
        const sort = localStorage.getItem('orders_sort_order') || 'asc';
        const res = await fetch(`/orders/fragment?sort=${sort}`);
        if (!res.ok) throw new Error('Fragment fetch failed');

        const html = await res.text();

        container.innerHTML = html;
        container.style.opacity = '1';

        const countEl = document.getElementById('orders-count');
        if (countEl) {
            const cards = container.querySelectorAll('[data-order-id]').length;
            countEl.textContent = `${cards} pedidos`;
        }

        if (typeof showToast === 'function') {
            showToast(' Pedidos actualizados', 'success');
        }
    } catch (err) {
        container.style.opacity = '1';
        location.reload();
    }
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────
function showNewOrdersToast(pendingCount) {
    if (newOrdersToastVisible) return;

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

function updateNavBadge(count) {
    const badge = document.getElementById('orders-nav-badge');
    if (!badge) return;
    if (count > 0) {
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

// ─── Audio ───────────────────────────────────────────────────────────────────
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

// ─── Toggle de sonido y notificaciones ────────────────────────────────────────
async function toggleSound() {
    soundEnabled = !soundEnabled;
    localStorage.setItem('velzia_sound_enabled', soundEnabled ? '1' : '0');

    const icon = document.getElementById('sound-icon');
    const btn = document.getElementById('sound-toggle-btn');

    if (soundEnabled) {
        unlockAudio();
        // Solicitar permiso de notificaciones al activar
        await requestNotificationPermission();

        if (icon) icon.textContent = 'notifications_active';
        if (btn) {
            btn.classList.add('bg-orange-100', 'dark:bg-orange-500/10', 'text-orange-500');
            btn.classList.remove('text-gray-400', 'dark:text-gray-500');
        }

        playNotificationSound();
        if (typeof showToast === 'function') {
            showToast(' Alertas y notificaciones activadas', 'success');
        }
    } else {
        if (icon) icon.textContent = 'notifications_off';
        if (btn) {
            btn.classList.remove('bg-orange-100', 'dark:bg-orange-500/10', 'text-orange-500');
            btn.classList.add('text-gray-400', 'dark:text-gray-500');
        }
        if (typeof showToast === 'function') {
            showToast(' Alertas desactivadas', 'default');
        }
    }
}

function restoreSoundPreference() {
    const saved = localStorage.getItem('velzia_sound_enabled');
    if (saved === '1') {
        soundEnabled = true;
        const icon = document.getElementById('sound-icon');
        const btn = document.getElementById('sound-toggle-btn');
        if (icon) icon.textContent = 'notifications_active';
        if (btn) {
            btn.classList.add('bg-orange-100', 'dark:bg-orange-500/10', 'text-orange-500');
            btn.classList.remove('text-gray-400', 'dark:text-gray-500');
        }
    }
}

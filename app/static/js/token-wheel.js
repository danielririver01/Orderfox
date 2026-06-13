/**
 * token-wheel.js (v3.0.0)
 * Sistema de monitoreo de tokens IA — Integrado en navegación
 */
document.addEventListener('DOMContentLoaded', () => {
    const sidebarCount = document.getElementById('sidebar-token-count');
    const sidebarBar = document.getElementById('sidebar-token-bar');
    const mobileCount = document.getElementById('mobile-token-count');

    if (!sidebarCount && !mobileCount) return;

    async function updateTokenStatus() {
        try {
            const data = await apiFetch('/api/tokens/status');
            const available = data.total_available || 0;
            const limit = data.plan_limit || 10;
            const percent = data.is_elite ? 100 : Math.max(0, Math.min(100, (available / limit) * 100));

            // Sidebar: token count
            if (sidebarCount) sidebarCount.textContent = available;

            // Sidebar: progress bar
            if (sidebarBar) {
                sidebarBar.style.width = percent + '%';

                sidebarBar.classList.remove('bg-orange-500', 'bg-yellow-500', 'bg-red-500', 'bg-emerald-500');
                if (data.is_elite) {
                    sidebarBar.classList.add('bg-emerald-500');
                } else if (available < 5) {
                    sidebarBar.classList.add('bg-red-500');
                } else if (available < limit * 0.3) {
                    sidebarBar.classList.add('bg-yellow-500');
                } else {
                    sidebarBar.classList.add('bg-orange-500');
                }
            }

            // Mobile: token count badge
            if (mobileCount) mobileCount.textContent = available;

        } catch (error) {
            console.error('VELZIA: Error actualizando tokens:', error);
        }
    }

    updateTokenStatus();
    window.addEventListener('focus', updateTokenStatus);
});

// Modal de tokens — funciones globales
window.openTokenModal = function () {
    const modal = document.getElementById('modal-tokens-recarga');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        document.body.style.overflow = 'hidden';
    }
};

window.closeTokenModal = function () {
    const modal = document.getElementById('modal-tokens-recarga');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.body.style.overflow = '';
    }
};

/**
 * Iniciar flujo de compra de tokens con MercadoPago
 */
window.initiateTokenPurchase = async function (packKey) {
    try {
        const data = await apiFetch('/api/tokens/topup/initiate', {
            method: 'POST',
            body: JSON.stringify({ pack: packKey })
        });

        if (data.checkout_url) {
            showToast('Iniciando pago seguro...', 'info');
            setTimeout(() => { window.location.href = data.checkout_url; }, 800);
        }

    } catch (error) {
        showToast(error.message || 'Error de conexión con la pasarela de pagos', 'error');
    }
};

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.closeTokenModal = window.closeTokenModal;
window.actionHandlers.openTokenModal = window.openTokenModal;
window.actionHandlers.initiateTokenPurchase = function(p) { window.initiateTokenPurchase(p.pack); };

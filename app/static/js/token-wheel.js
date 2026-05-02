/**
 * token-wheel.js (v2.0.0 Alpha)
 * Sistema de monitoreo global de tokens IA
 */
document.addEventListener('DOMContentLoaded', () => {
    const bubbleContainer = document.getElementById('token-floating-bubble');

    if (!bubbleContainer) {
        return;
    }

    const bubbleProgress = document.getElementById('token-bubble-progress');
    const bubbleValue = document.getElementById('token-bubble-value');
    const tooltipText = document.getElementById('token-tooltip-text');

    const CIRCUMFERENCE = 150.8;

    async function updateTokenStatus() {
        try {
            const response = await fetch('/api/tokens/status');

            if (!response.ok) throw new Error('No autorizado');

            const data = await response.json();

            // Mostrar el globo con una pequeña transición
            bubbleContainer.classList.add('is-ready');

            if (data.is_elite) {
                // Mostramos el número y le pasamos el valor de la API
                if (bubbleValue) {
                    bubbleValue.classList.remove('hidden');
                    bubbleValue.textContent = data.total_available;
                }

                bubbleContainer.classList.add('is-elite');

                if (bubbleProgress) {
                    bubbleProgress.classList.remove('critical', 'warning');
                    bubbleProgress.classList.add('success');
                    bubbleProgress.style.strokeDashoffset = 0; // Círculo completo
                }

                if (tooltipText) tooltipText.textContent = `Plan Élite: ${data.total_available} tokens disponibles`;
            } else {
                if (bubbleValue) bubbleValue.classList.remove('hidden');
                bubbleContainer.classList.remove('is-elite');

                const available = data.total_available;
                const limit = data.plan_limit || 10;
                const percent = Math.max(0, Math.min(100, (available / limit) * 100));

                if (bubbleValue) bubbleValue.textContent = available;
                if (tooltipText) tooltipText.textContent = `${available} tokens disponibles`;

                if (bubbleProgress) {
                    const offset = CIRCUMFERENCE - (percent / 100 * CIRCUMFERENCE);
                    bubbleProgress.style.strokeDashoffset = offset;

                    // Colores
                    bubbleProgress.classList.remove('success', 'warning', 'critical');
                    if (available < 5) bubbleProgress.classList.add('critical');
                    else if (available < (limit * 0.3)) bubbleProgress.classList.add('warning');
                    else bubbleProgress.classList.add('success');
                }
            }
        } catch (error) {
            console.error('VELZIA: Error actualizando tokens:', error);
        }
    }

    updateTokenStatus();
    window.addEventListener('focus', updateTokenStatus);
});

// Funciones para apertura de modal de compra (globale)
window.openTokenModal = function () {
    const modal = document.getElementById('modal-tokens-recarga');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }
};

window.closeTokenModal = function () {
    const modal = document.getElementById('modal-tokens-recarga');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }
};

/**
 * Iniciar flujo de compra de tokens con MercadoPago
 */
window.initiateTokenPurchase = async function (packKey) {
    try {
        showToast('Iniciando pago seguro...', 'info');

        const response = await fetch('/api/tokens/topup/initiate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pack: packKey })
        });

        const data = await response.json();

        if (!response.ok) {
            const errorMsg = data.error || 'Error al iniciar pago';
            showToast(errorMsg, 'warning');
            return;
        }

        if (data.checkout_url) {
            // Redirigir a MercadoPago
            window.location.href = data.checkout_url;
        }

    } catch (error) {
        //console.error('VELZIA: Error en compra de tokens:', error);
        showToast('Error de conexión con la pasarela de pagos', 'error');
    }
};

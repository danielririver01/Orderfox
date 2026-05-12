/**
 * Order Detail Panel - Velzia
 * Desktop: inline sticky panel | Mobile: full page navigation
 */

let currentOrderId = null;

function isMobile() {
    return window.innerWidth < 768;
}

function openOrderDetail(orderId) {
    if (isMobile()) {
        window.location.href = `/orders/${orderId}`;
        return;
    }

    currentOrderId = orderId;
    const panel = document.getElementById('order-detail-panel');
    const content = document.getElementById('order-detail-content');
    const loading = document.getElementById('order-detail-loading');
    const listWrapper = document.getElementById('orders-list-wrapper');

    if (!panel || !content || !listWrapper) return;

    // Lock body scroll
    document.body.style.overflow = 'hidden';

    // Show panel
    panel.classList.remove('hidden');
    panel.classList.add('md:block');

    // Change grid to 2 columns when panel is open
    listWrapper.classList.remove('md:grid-cols-3');
    listWrapper.classList.add('md:grid-cols-2');

    // Show loading, hide content
    content.classList.add('hidden');
    content.classList.remove('flex');
    loading.classList.remove('hidden');
    loading.classList.add('flex');

    fetch(`/orders/${orderId}/fragment`)
        .then(res => {
            if (!res.ok) throw new Error('Error al cargar el pedido');
            return res.text();
        })
        .then(html => {
            loading.classList.add('hidden');
            loading.classList.remove('flex');
            content.innerHTML = html;
            content.classList.remove('hidden');
            content.classList.add('flex');

            document.querySelectorAll('[data-order-id]').forEach(card => {
                card.classList.remove('ring-2', 'ring-[#f2460d]', 'ring-offset-2', 'ring-offset-[#0a0a0a]');
            });
            const selectedCard = document.querySelector(`[data-order-id="${orderId}"]`);
            if (selectedCard) {
                selectedCard.classList.add('ring-2', 'ring-[#f2460d]', 'ring-offset-2', 'ring-offset-[#0a0a0a]');
            }
        })
        .catch(err => {
            loading.classList.add('hidden');
            loading.classList.remove('flex');
            content.innerHTML = `
                <div class="flex-1 flex items-center justify-center p-8">
                    <div class="text-center">
                        <span class="material-symbols-outlined text-red-500 text-[32px] mb-2">error</span>
                        <p class="text-red-400 text-sm">${err.message}</p>
                        <button onclick="openOrderDetail(${orderId})" class="mt-3 text-[10px] text-gray-500 hover:text-white uppercase tracking-widest font-bold">Reintentar</button>
                    </div>
                </div>
            `;
            content.classList.remove('hidden');
            content.classList.add('flex');
        });
}

function closeOrderDetail() {
    const panel = document.getElementById('order-detail-panel');
    const content = document.getElementById('order-detail-content');
    const listWrapper = document.getElementById('orders-list-wrapper');

    // Restore body scroll
    document.body.style.overflow = '';

    if (panel) {
        panel.classList.add('hidden');
        panel.classList.remove('md:block');
    }
    if (listWrapper) {
        listWrapper.classList.remove('md:grid-cols-2');
        listWrapper.classList.add('md:grid-cols-3');
    }
    if (content) {
        content.classList.add('hidden');
        content.classList.remove('flex');
        content.innerHTML = '';
    }

    document.querySelectorAll('[data-order-id]').forEach(card => {
        card.classList.remove('ring-2', 'ring-[#f2460d]', 'ring-offset-2', 'ring-offset-[#0a0a0a]');
    });

    currentOrderId = null;
}

function refreshOrderPanel(orderId) {
    if (currentOrderId === orderId) {
        openOrderDetail(orderId);
    }
}

// WhatsApp contact helper
function contactWhatsApp(phone, orderNumber) {
    const cleanPhone = phone.replace(/\D/g, '');
    const message = `Hola! Te contacto sobre tu pedido ${orderNumber}`;
    window.open(`https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`, '_blank');
}

// Cancel order from panel
function cancelOrderPanel(orderId) {
    if (!confirm('¿Cancelar este pedido?')) return;
    const form = document.getElementById('cancelOrderFormPanel');
    if (form) form.submit();
}

// Keyboard shortcut: Escape to close panel
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && currentOrderId && !isMobile()) {
        closeOrderDetail();
    }
});

// Función para contactar por WhatsApp al cliente
function contactWhatsApp(phone, orderNumber, restaurantName) {
    let cleanPhone = phone.replace(/\D/g, '');
    if (!cleanPhone.startsWith('57')) {
        cleanPhone = '57' + cleanPhone;
    }

    let message = `*MENÚ*\n`;
    message += `------------------------------\n`;
    message += `¡Hola! Tu pedido ya está *LISTO*.\n\n`;
    message += `Orden: \`\`\`${orderNumber}\`\`\`\n`;
    message += `------------------------------\n`;
    message += `_Gracias por tu preferencia_`;

    const url = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`;
    window.open(url, '_blank');
}

// Función para cambiar el estado de un pedido con redirección
async function changeStatus(orderId, newStatus, redirectUrl) {
    try {
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
        const response = await fetch(`/orders/${orderId}/status`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ status: newStatus })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || 'Error al cambiar estado');
        }

        if (redirectUrl) {
            location.href = redirectUrl;
        } else {
            location.reload();
        }
    } catch (error) {
        window.showToast(error.message, 'error');
    }
}
// Modal de cancelación
function showCancelModal() {
    const modal = document.getElementById('cancelModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function hideCancelModal() {
    const modal = document.getElementById('cancelModal');
    modal.classList.add('hidden');
    document.body.style.overflow = 'auto';
}

function confirmCancelOrder() {
    document.getElementById('cancelOrderForm').submit();
}

// Cerrar con Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideCancelModal();
});

// Event delegation handlers
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.contactWhatsApp = (p) => contactWhatsApp(p.phone, p.number);
window.actionHandlers.openReceipt = (p) => window.open(p.url, '_blank');
window.actionHandlers.changeStatusDetail = (p) => changeStatus(parseInt(p.id), p.status, p.url);
window.actionHandlers.showCancelModal = showCancelModal;
window.actionHandlers.hideCancelModal = hideCancelModal;
window.actionHandlers.confirmCancelOrder = confirmCancelOrder;
window.actionHandlers.openDeleteModal = (p) => openDeleteModal(document.getElementById(p.form), p.message, p.title);
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

//Para changeStatus, necesitas pasar el orderId como parámetro
async function changeStatus(orderId, newStatus, redirectUrl) {
    try {
        const response = await fetch(`/orders/${orderId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Error al cambiar estado');
        }
        
        location.href = redirectUrl;
    } catch (error) {
        alert(error.message);
    }
}
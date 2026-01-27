// Cart State
let cart = JSON.parse(localStorage.getItem('velziaCart')) || {};

// Initialize display
document.addEventListener('DOMContentLoaded', () => {
    updateDisplay();
});

function updateQty(id, delta) {
    const productElement = document.querySelector(`.product-card[data-id="${id}"]`);
    if (!productElement) return;

    const name = productElement.dataset.name;
    const price = parseInt(productElement.dataset.price);

    if (!cart[id]) {
        cart[id] = { name, price, quantity: 0, extras: [] };
    }

    cart[id].quantity += delta;

    if (cart[id].quantity <= 0) {
        // Reset and hide extras
        const extrasContainer = document.getElementById(`extras-${id}`);
        if (extrasContainer) {
            extrasContainer.style.display = 'none';
            extrasContainer.querySelectorAll('input').forEach(i => i.checked = false);
        }
        delete cart[id];
    } else {
        // Show extras if they exist
        const extrasContainer = document.getElementById(`extras-${id}`);
        if (extrasContainer) {
            extrasContainer.style.display = 'block';
        }
    }

    localStorage.setItem('velziaCart', JSON.stringify(cart));
    updateDisplay();
}

function updateExtra(productId) {
    if (!cart[productId]) return;

    const extrasContainer = document.getElementById(`extras-${productId}`);
    const selectedExtras = [];
    
    extrasContainer.querySelectorAll('.extra-checkbox:checked').forEach(checkbox => {
        selectedExtras.push({
            name: checkbox.dataset.name,
            price: parseInt(checkbox.dataset.price)
        });
    });

    cart[productId].extras = selectedExtras;
    localStorage.setItem('velziaCart', JSON.stringify(cart));
    updateDisplay();
}

function clearCart() {
    cart = {};
    localStorage.removeItem('velziaCart');

    document.querySelectorAll('.qty-display')
        .forEach(el => el.textContent = '0');

    document.querySelectorAll('.extras-container')
        .forEach(el => el.style.display = 'none');

    document.querySelectorAll('.extra-checkbox')
        .forEach(cb => cb.checked = false);

    updateDisplay();
    showToast('Carrito vaciado', 'success');
}



function updateDisplay() {
    let total = 0;
    let itemCount = 0;

    // Reset all qty displays present in current view
    document.querySelectorAll('.qty-display').forEach(el => el.textContent = '0');

    // Update displays for items in cart
    for (const id in cart) {
        const item = cart[id];
        const display = document.getElementById(`qty-${id}`);
        const extrasContainer = document.getElementById(`extras-${id}`);

        if (display) {
            display.textContent = item.quantity;
        }
        
        if (extrasContainer && item.quantity > 0) {
            extrasContainer.style.display = 'block';
            // Mark checkboxes from storage
            item.extras.forEach(extra => {
                const cb = extrasContainer.querySelector(`.extra-checkbox[data-name="${extra.name}"]`);
                if (cb) cb.checked = true;
            });
        }

        // Calculate total
        const extrasTotal = item.extras.reduce((sum, e) => sum + e.price, 0);
        total += (item.price + extrasTotal) * item.quantity;
        itemCount += item.quantity;
    }

    // Update sticky cart
    const stickyCart = document.getElementById('sticky-cart');
    const cartTotalDisplay = document.getElementById('cart-total');
    
    if (itemCount > 0) {
        stickyCart.style.display = 'block';
        cartTotalDisplay.textContent = `$${total.toLocaleString('es-CO')}`;
    } else {
        stickyCart.style.display = 'none';
    }
}

async function sendWhatsApp() {
    if (Object.keys(cart).length === 0) return;

    // --- Anti-spam Frontend (90s window) ---
    const lastOrderTime = localStorage.getItem('velziaLastOrder');
    const now = Date.now();
    const waitTime = 90 * 1000; // 90 segundos

    if (lastOrderTime && (now - lastOrderTime < waitTime)) {
        const remaining = Math.ceil((waitTime - (now - lastOrderTime)) / 1000);
        showToast(`¿Olvidaste algo? Espera ${remaining} seg para enviar otro pedido `, 'info');
        return;
    }
    // ---------------------------

    const btn = document.querySelector('.btn-send');
    const originalText = btn.innerHTML;
    
    try {
        btn.disabled = true;
        btn.innerHTML = 'Procesando...';

        // 1. Calcular total para el backend
        let total = 0;
        for (const id in cart) {
            const item = cart[id];
            const extrasTotal = item.extras.reduce((sum, e) => sum + e.price, 0);
            total += (item.price + extrasTotal) * item.quantity;
        }

        // 2. Registrar en base de datos
        const response = await fetch('/menu/api/order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                cart, 
                total,
                restaurant_id: window.restaurantId 
            })
        });

        const result = await response.json();
        
        if (!result.success) throw new Error(result.error);

        // Registrar tiempo del pedido exitoso para anti-spam
        localStorage.setItem('velziaLastOrder', Date.now());

        // 3. Preparar mensaje de WhatsApp
        // 3. Preparar mensaje de WhatsApp con formato Markdown profesional
        let message = `*NUEVO PEDIDO RECIBIDO*\n`; // Negrita para el encabezado
        message += `N° del pedido: \`\`\`${result.order_number}\`\`\`\n`;
        message += `------------------------------\n`;

        for (const id in cart) {
            const item = cart[id];
            
            // Usamos "-" para que WhatsApp active el formato de lista con sangría [4]
            // Usamos "*" para resaltar la cantidad del producto
            message += `- *${item.quantity}x* ${item.name}\n`;

            if (item.extras.length > 0) {
                const extrasList = item.extras.map(e => e.name).join(', ');
                // Usamos "_" para poner los extras en cursiva y crear jerarquía visual [4]
                message += `  _↳ Extras: ${extrasList}_\n`;
            }
        }

        // Resaltamos el monto final para facilitar el cobro rápido
        message += `\n*TOTAL A PAGAR: $${total.toLocaleString('es-CO')}*\n`;
        message += `------------------------------\n`;
        message += `_Gracias por tu pedido_`; // Cursiva para el pie de mensaje [4]

        // Número dinámico desde backend
        const businessPhone = window.businessPhone;
        const url = `https://wa.me/${businessPhone}?text=${encodeURIComponent(message)}`;

        window.open(url, '_blank');
        
    } catch (error) {
        showToast('Error al registrar el pedido: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

 function showToast(message, type = 'default') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `<span>${message}</span>`;
            
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(-20px)';
                toast.style.transition = 'all 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        }
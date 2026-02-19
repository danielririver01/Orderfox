// Cart State Configuration
const CART_KEY = window.CART_KEY || `velziaCart_${window.restaurantId || 'default'}`;
const CART_TTL = 24 * 60 * 60 * 1000; // 24 hours

// Load Cart with TTL validation
function loadCart() {
    try {
        const stored = localStorage.getItem(CART_KEY);
        if (!stored) return {};
        
        const cartData = JSON.parse(stored);
        const now = Date.now();
        
        // TTL Check: If older than 24h, clear it
        if (cartData._lastUpdated && (now - cartData._lastUpdated > CART_TTL)) {
            console.log("Cart expired, clearing...");
            localStorage.removeItem(CART_KEY);
            return {};
        }
        
        return cartData.items || {};
    } catch (e) {
        console.error("Error loading cart:", e);
        return {};
    }
}

let cart = loadCart();

// Initialize display and sync
document.addEventListener('DOMContentLoaded', () => {
    updateDisplay();
});

// Sync across tabs
window.addEventListener('storage', (event) => {
    if (event.key === CART_KEY) {
        cart = loadCart();
        updateDisplay();
    }
});

function saveCart() {
    const cartData = {
        items: cart,
        _lastUpdated: Date.now()
    };
    localStorage.setItem(CART_KEY, JSON.stringify(cartData));
}

function updateQty(id, delta) {
    if (!window.menuAvailable) {
        showToast('El menú no está recibiendo pedidos ahora', 'info');
        return;
    }

    const productElement = document.querySelector(`.product-card[data-id="${id}"]`);
    if (!productElement) return;

    const name = productElement.dataset.name;
    const price = parseInt(productElement.dataset.price);

    if (!cart[id]) {
        cart[id] = { name, price, quantity: 0, extras: [] };
    }

    cart[id].quantity += delta;

    if (cart[id].quantity <= 0) {
        const extrasContainer = document.getElementById(`extras-${id}`);
        if (extrasContainer) {
            extrasContainer.style.display = 'none';
            extrasContainer.querySelectorAll('input').forEach(i => i.checked = false);
        }
        delete cart[id];
    } else {
        const extrasContainer = document.getElementById(`extras-${id}`);
        if (extrasContainer) {
            extrasContainer.style.display = 'block';
        }
    }

    saveCart();
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
    saveCart();
    updateDisplay();
}

function clearCart(silent = false) {
    cart = {};
    localStorage.removeItem(CART_KEY);

    document.querySelectorAll('.qty-display').forEach(el => el.textContent = '0');
    document.querySelectorAll('.extras-container').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.extra-checkbox').forEach(cb => cb.checked = false);

    updateDisplay();
    if (!silent) showToast('Carrito vaciado', 'success');
}

function updateDisplay() {
    let total = 0;
    let itemCount = 0;

    // Reset displays
    document.querySelectorAll('.qty-display').forEach(el => el.textContent = '0');

    // Contextual Block: If menu is not available, hide cart and stop
    const stickyCart = document.getElementById('sticky-cart');
    if (window.menuAvailable === false || !document.querySelector('.product-card')) {
        if (stickyCart) stickyCart.style.display = 'none';
        return; 
    }

    // Update displays from state
    for (const id in cart) {
        const item = cart[id];
        const display = document.getElementById(`qty-${id}`);
        const extrasContainer = document.getElementById(`extras-${id}`);

        if (display) display.textContent = item.quantity;
        
        if (extrasContainer && item.quantity > 0) {
            extrasContainer.style.display = 'block';
            item.extras.forEach(extra => {
                const cb = extrasContainer.querySelector(`.extra-checkbox[data-name="${extra.name}"]`);
                if (cb) cb.checked = true;
            });
        }

        const extrasTotal = item.extras.reduce((sum, e) => sum + e.price, 0);
        total += (item.price + extrasTotal) * item.quantity;
        itemCount += item.quantity;
    }

    const cartTotalDisplay = document.getElementById('cart-total');
    if (itemCount > 0) {
        if (stickyCart) stickyCart.style.display = 'block';
        if (cartTotalDisplay) cartTotalDisplay.textContent = `$${total.toLocaleString('es-CO')}`;
    } else {
        if (stickyCart) stickyCart.style.display = 'none';
    }
}

async function sendWhatsApp() {
    if (Object.keys(cart).length === 0) return;

    const lastOrderTime = localStorage.getItem('velziaLastOrder');
    const now = Date.now();
    const waitTime = 90 * 1000;

    if (lastOrderTime && (now - lastOrderTime < waitTime)) {
        const remaining = Math.ceil((waitTime - (now - lastOrderTime)) / 1000);
        showToast(`¿Olvidaste algo? Espera ${remaining} seg para enviar otro pedido`, 'info');
        return;
    }

    const btn = document.querySelector('.btn-send');
    const originalText = btn ? btn.innerHTML : '';
    
    try {
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = 'Procesando...';
        }

        let total = 0;
        for (const id in cart) {
            const item = cart[id];
            const extrasTotal = item.extras.reduce((sum, e) => sum + e.price, 0);
            total += (item.price + extrasTotal) * item.quantity;
        }

        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken;

        const response = await fetch('/menu/api/order', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ 
                cart, 
                total,
                restaurant_id: window.restaurantId 
            })
        });

        const text = await response.text();
        let result;
        try {
            result = JSON.parse(text);
        } catch (e) {
            throw new Error("Respuesta inválida del servidor");
        }
        
        if (!result.success) throw new Error(result.error);

        localStorage.setItem('velziaLastOrder', Date.now());

        let message = `*NUEVO PEDIDO RECIBIDO*\n`;
        message += `N° del pedido: \`\`\`${result.order_number}\`\`\`\n`;
        if (result.table_name) message += `📍 *Mesa:* ${result.table_name}\n`;
        message += `------------------------------\n`;

        for (const id in cart) {
            const item = cart[id];
            message += `- *${item.quantity}x* ${item.name}\n`;
            if (item.extras.length > 0) {
                const extrasList = item.extras.map(e => e.name).join(', ');
                message += `  _↳ Extras: ${extrasList}_\n`;
            }
        }

        message += `\n*TOTAL A PAGAR: $${total.toLocaleString('es-CO')}*\n`;
        message += `------------------------------\n`;
        message += `_Gracias por tu pedido_`;

        const businessPhone = window.businessPhone;
        const url = `https://wa.me/${businessPhone}?text=${encodeURIComponent(message)}`;

        window.open(url, '_blank');
        
        // --- KEY FIX: Clear cart AFTER opening WhatsApp ---
        clearCart(true); // silent = true
        
    } catch (error) {
        showToast('Error al registrar el pedido: ' + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

function showToast(message, type = 'default') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
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

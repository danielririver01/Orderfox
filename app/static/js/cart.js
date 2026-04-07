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
        
        // Capturar extras si el usuario los seleccionó antes de presionar '+'
        const extrasContainer = document.getElementById(`extras-${id}`);
        if (extrasContainer) {
            extrasContainer.querySelectorAll('.extra-checkbox:checked').forEach(checkbox => {
                cart[id].extras.push({
                    id: checkbox.dataset.id,
                    name: checkbox.dataset.name,
                    price: parseInt(checkbox.dataset.price)
                });
            });
        }
    }

    cart[id].quantity += delta;

    if (cart[id].quantity <= 0) {
        const extrasContainer = document.getElementById(`extras-${id}`);
        if (extrasContainer) {
            extrasContainer.querySelectorAll('input').forEach(i => i.checked = false);
        }
        delete cart[id];
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
            id: checkbox.dataset.id,
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
    document.querySelectorAll('.extra-checkbox').forEach(cb => cb.checked = false);
    
    // Limpiar campos del modal de entrega
    ['delivery-name', 'delivery-city', 'delivery-address', 'user_secondary_email'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    updateDisplay();
    if (!silent) showToast('Carrito vaciado', 'success');
}

function updateDisplay() {
    let total = 0;
    let itemCount = 0;

    // Reset displays
    document.querySelectorAll('.qty-display').forEach(el => el.textContent = '0');

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
        if (stickyCart && (document.getElementById('address-modal')?.classList.contains('hidden') !== false)) {
            stickyCart.style.display = 'block';
        }
        if (cartTotalDisplay) cartTotalDisplay.textContent = `$${total.toLocaleString('es-CO')}`;
    } else {
        if (stickyCart) stickyCart.style.display = 'none';
    }
}

// Modal de Dirección
function openAddressModal() {
    const modal = document.getElementById('address-modal');
    const stickyCart = document.getElementById('sticky-cart');
    
    // Iniciar timestamp en servidor para anti-bots
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    fetch('/menu/api/init-checkout', { 
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ restaurant_id: window.restaurantId })
    });

    if (modal) {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        if (stickyCart) stickyCart.style.display = 'none';
    }
}

function closeAddressModal() {
    const modal = document.getElementById('address-modal');
    const stickyCart = document.getElementById('sticky-cart');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
        if (stickyCart && Object.keys(cart).length > 0) {
            stickyCart.style.display = 'block';
        }
    }
}

async function processOrderWithAddress() {
    const fields = {
        'delivery-name': 'Nombre',
        'delivery-phone': 'Teléfono',
        'delivery-city': 'Ciudad',
        'delivery-address': 'Dirección'
    };

    let hasError = false;
    let values = {};

    Object.keys(fields).forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            let val = el.value.trim();
            // Si es teléfono, quitar espacios o guiones
            if (id === 'delivery-phone') {
                val = val.replace(/[-\s]/g, '');
            }
            values[id] = val;
            
            let isValid = val !== '';
            
            // Validación estricta para teléfonos móviles de Colombia (Inicia en 3, 10 dígitos)
            if (id === 'delivery-phone' && val) {
                isValid = /^3\d{9}$/.test(val);
                if (!isValid) {
                    showToast('El teléfono debe tener 10 dígitos y comenzar con 3', 'error');
                }
            }

            if (!isValid) {
                hasError = true;
                // Resaltar en rojo
                el.classList.remove('border-gray-100', 'dark:border-[#262626]');
                el.classList.add('border-red-500', 'dark:border-red-500', 'animate-pulse');
                
                // Quitar resalto después de 3s
                setTimeout(() => {
                    el.classList.remove('border-red-500', 'dark:border-red-500', 'animate-pulse');
                    el.classList.add('border-gray-100', 'dark:border-[#262626]');
                }, 3000);
            }
        }
    });

    const honeypot = document.getElementById('user_secondary_email')?.value || '';

    if (hasError) {
        showToast('Faltan datos requeridos (marcados en rojo)', 'warning');
        return;
    }

    closeAddressModal();
    await performCheckout(values['delivery-city'], values['delivery-address'], values['delivery-name'], honeypot, values['delivery-phone']);
}

async function sendWhatsApp() {
    if (Object.keys(cart).length === 0) return;

    if (window.isTableOrder) {
        await performCheckout();
    } else {
        openAddressModal();
    }
}

async function performCheckout(city = null, address = null, customerName = null, honeypot = "", phone = "") {
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
                restaurant_id: window.restaurantId,
                city,
                address,
                customer_name: customerName,
                customer_phone: phone,
                user_secondary_email: honeypot
            })
        });

        const result = await response.json();
        
        if (!result.success) {
            const errorMsg = result.error;
            const retryAfter = result.retry_after;
            if (retryAfter) {
                showToast(`${errorMsg} (${retryAfter}s)`, 'warning');
            } else {
                throw new Error(errorMsg);
            }
            return;
        }

        // --- NUEVO FLUJO: MODAL DE ÉXITO ---
        showOrderSuccessModal(result);
        
        // Limpiar carrito al registrar éxito en servidor
        clearCart(true);

    } catch (error) {
        showToast('Error al registrar el pedido: ' + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

// Variables temporales para el modal de éxito
let currentOrderData = null;

function showOrderSuccessModal(result) {
    currentOrderData = result;
    
    const modal = document.getElementById('order-success-modal');
    const orderBadge = document.getElementById('success-order-number');
    const totalDisplay = document.getElementById('success-order-total');
    
    // Configuración dinámica para pedidos desde mesa
    const description = document.getElementById('success-modal-description');
    const whatsappBtn = document.getElementById('btn-confirm-whatsapp');
    const backBtn = document.getElementById('btn-volver-menu');

    if (window.isTableOrder) {
        if (description) {
            description.innerHTML = `Tu pedido ha sido enviado a la cocina. <br><strong class="text-orange-600 dark:text-orange-400">¡Lo traeremos a tu mesa pronto!</strong>`;
        }
        if (whatsappBtn) {
            whatsappBtn.style.display = 'none';
        }
        if (backBtn) {
            backBtn.textContent = 'Volver al Menú / Pedir más';
            // Aplicar estilo de botón primario para resaltar la acción
            backBtn.className = "w-full flex items-center justify-center gap-2 bg-gray-900 dark:bg-white dark:text-black text-white py-4 px-6 rounded-full font-black text-sm uppercase tracking-widest transition-all duration-300 shadow-xl active:scale-95 outline-none";
        }
    } else {
        // Reset por si acaso (flujo normal de domicilios)
        if (whatsappBtn) whatsappBtn.style.display = 'flex';
    }
    
    if (orderBadge) orderBadge.textContent = result.order_number;
    if (totalDisplay) totalDisplay.textContent = `$${result.total.toLocaleString('es-CO')}`;
    
    if (modal) {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }
}

function confirmAndRedirectWhatsApp() {
    if (!currentOrderData) return;

    const data = currentOrderData;
    const customerName = data.customer_name || 'un cliente';
    const message = `Hola, soy ${customerName}. Pedido Nº ${data.order_number} realizado. ¿Me confirmas por favor?`;

    const businessPhone = window.businessPhone;
    const url = `https://wa.me/${businessPhone}?text=${encodeURIComponent(message)}`;
    
    window.open(url, '_blank');
    location.reload(); // Refrescar para limpiar estado visual completo
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

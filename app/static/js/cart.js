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

    // Si el producto no está en el carrito, intentamos obtener sus datos del DOM
    if (!cart[id]) {
        const productElement = document.querySelector(`.product-card[data-id="${id}"]`);
        if (!productElement) return;

        const name = productElement.dataset.name;
        const price = parseInt(productElement.dataset.price);
        const imageUrl = productElement.querySelector('.product-image')?.src || null;

        cart[id] = { 
            name, 
            price, 
            quantity: 0, 
            extras: [],
            imageUrl: imageUrl
        };
        
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

    // Cerrar sidebar si está abierto al vaciar
    const sidebar = document.getElementById('cart-sidebar');
    if (sidebar && sidebar.classList.contains('open')) {
        toggleCart();
    }

    if (!silent) showToast('Carrito vaciado', 'success');
}

function toggleCart() {
    const sidebar = document.getElementById('cart-sidebar');
    const overlay = document.getElementById('cart-overlay');
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('open');
    
    if (sidebar && sidebar.classList.contains('open')) {
        document.body.classList.add('cart-open');
    } else {
        document.body.classList.remove('cart-open');
    }
}

function removeFromCart(id) {
    if (cart[id]) {
        delete cart[id];
        saveCart();
        updateDisplay();
        showToast('Producto eliminado', 'info');
    }
}

function updateDisplay() {
    let total = 0;
    let itemCount = 0;

    // Reset displays de cantidad en las cards de productos
    document.querySelectorAll('.qty-display').forEach(el => el.textContent = '0');

    const cartList = document.getElementById('cart-items-list');
    const cartBtn = document.getElementById('cart-toggle-btn');
    const cartBadge = document.getElementById('cart-count-badge');
    const sidebarTotal = document.getElementById('sidebar-cart-total');

    if (!cartList) return;

    cartList.innerHTML = ''; // Limpiar lista

    // Verdad absoluta desde el servidor para disponibilidad
    if (window.menuAvailable === false || !document.querySelector('.product-card')) {
        if (cartBtn) cartBtn.style.display = 'none';
        return; 
    }

    const itemsArray = Object.entries(cart);

    if (itemsArray.length === 0) {
        cartList.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-20">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                </svg>
                <p class="font-bold uppercase tracking-widest text-xs">El carrito está vacío</p>
            </div>
        `;
        if (cartBtn) cartBtn.classList.add('hidden');
        if (sidebarTotal) sidebarTotal.textContent = '$0';
        
        // Cerrar sidebar si se vacía y está abierto
        const sidebar = document.getElementById('cart-sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            // toggleCart(); // Comentado para no molestar al usuario si lo acaba de vaciar
        }
    } else {
        if (cartBtn) cartBtn.classList.remove('hidden');

        itemsArray.forEach(([id, item]) => {
            const display = document.getElementById(`qty-${id}`);
            if (display) display.textContent = item.quantity;

            // Calcular subtotal del item incluyendo extras
            const extrasTotal = item.extras.reduce((sum, e) => sum + e.price, 0);
            const itemSubtotal = (item.price + extrasTotal) * item.quantity;
            total += itemSubtotal;
            itemCount += item.quantity;

            // Generar Iniciales para fallback
            const initials = item.name.substring(0, 2).toUpperCase();

            // Renderizar Item en la lista
            const itemEl = document.createElement('div');
            itemEl.className = 'cart-item';
            itemEl.innerHTML = `
                <div class="cart-item-icon">
                    ${item.imageUrl ? `<img src="${item.imageUrl}" class="cart-item-image" alt="${item.name}">` : `<span class="cart-item-letters">${initials}</span>`}
                    <button onclick="removeFromCart(${id})" class="cart-item-delete">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
                <div class="cart-item-info">
                    <h4 class="cart-item-name">${item.name}</h4>
                    <div class="cart-item-meta">
                        <div class="sidebar-qty-controls">
                            <button class="btn-sidebar-qty" onclick="updateQty(${id}, -1)">-</button>
                            <span class="sidebar-qty-num">${item.quantity}</span>
                            <button class="btn-sidebar-qty" onclick="updateQty(${id}, 1)">+</button>
                        </div>
                        <span class="cart-item-price">$${itemSubtotal.toLocaleString('es-CO')}</span>
                    </div>
                </div>
            `;
            cartList.appendChild(itemEl);

        });

        if (sidebarTotal) sidebarTotal.textContent = `$${total.toLocaleString('es-CO')}`;
        if (cartBadge) cartBadge.textContent = itemCount;
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
            btn.innerHTML = `
                <svg class="animate-spin h-4 w-4 mr-2 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="vertical-align: middle;">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Procesando...
            `;
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

        // --- NUEVO FLUJO: REDIRECCIÓN MERCADO PAGO O MODAL DE ÉXITO ---
        if (result.init_point) {
            showToast('¡Pedido creado! Redirigiendo al pago...', 'success');
            // Limpiar carrito antes de irnos
            clearCart(true);
            // Redirigir a Mercado Pago
            window.location.href = result.init_point;
        } else {
            showOrderSuccessModal(result);
            clearCart(true);
        }

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

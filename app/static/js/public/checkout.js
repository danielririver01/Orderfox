/**
 * checkout.js - Flujo de checkout y pedidos
 * Dependencias: mpLoadCart, showToast, updateCartSummaryDisplay, updateQtyBadges (cart-core.js)
 */

// ===== CHECKOUT STATE =====
var currentOrderData = null;

// ===== OPEN CHECKOUT MODAL =====
function openCheckoutModal() {
    var cart = mpLoadCart();
    if (Object.keys(cart).length === 0) {
        showToast('Agrega productos al pedido primero', 'warning');
        return;
    }

    // Anti-bot
    var csrf = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = csrf ? csrf.getAttribute('content') : null;
    var headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
    fetch('/menu/api/init-checkout', { method: 'POST', headers: headers, body: JSON.stringify({ restaurant_id: window.restaurantId }) });

    document.getElementById('address-modal').classList.add('visible');
    document.body.style.overflow = 'hidden';
}
window.openCheckoutModal = openCheckoutModal;

// ===== CLOSE ADDRESS MODAL =====
function closeAddressModal() {
    document.getElementById('address-modal').classList.remove('visible');
    document.body.style.overflow = '';
}
window.closeAddressModal = closeAddressModal;

// ===== PROCESS ORDER WITH ADDRESS =====
function processOrderWithAddress() {
    var fields = {
        'delivery-name': 'Nombre',
        'delivery-phone': 'Teléfono',
        'delivery-address': 'Dirección'
    };

    var hasError = false;
    var values = {};

    Object.keys(fields).forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        var val = el.value.trim();
        if (id === 'delivery-phone') val = val.replace(/[-\s]/g, '');
        values[id] = val;

        var isValid = val !== '';
        if (id === 'delivery-phone' && val) {
            isValid = /^3\d{9}$/.test(val);
            if (!isValid) showToast('El teléfono debe tener 10 dígitos y empezar con 3', 'error');
        }
        if (!isValid) {
            hasError = true;
            el.style.borderColor = '#ef4444';
            setTimeout(function () { el.style.borderColor = ''; }, 3000);
        }
    });

    if (hasError) { showToast('Faltan datos requeridos', 'warning'); return; }

    closeAddressModal();
    performCheckout(values['delivery-address'], values['delivery-name'], values['delivery-phone']);
}
window.processOrderWithAddress = processOrderWithAddress;

// ===== PERFORM CHECKOUT =====
function performCheckout(address, customerName, phone) {
    var cart = mpLoadCart();

    // Transformar carrito: el backend espera product_id como key
    var serverCart = {};
    var total = 0;
    for (var key in cart) {
        var item = cart[key];
        var pid = item.productId || parseInt(key.split('_')[0]);
        var extrasTotal = (item.extras || []).reduce(function (s, e) { return s + e.price; }, 0);
        total += (item.price + extrasTotal) * item.quantity;

        // Si ya existe ese product_id, sumar cantidad
        if (serverCart[pid]) {
            serverCart[pid].quantity += item.quantity;
        } else {
            serverCart[pid] = {
                quantity: item.quantity,
                extras: item.extras || []
            };
        }
    }

    var csrf = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = csrf ? csrf.getAttribute('content') : null;
    var headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    fetch('/menu/api/order', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
            cart: serverCart,
            total: total,
            restaurant_id: window.restaurantId,
            address: address,
            customer_name: customerName,
            customer_phone: phone,
            user_secondary_email: ''
        })
    })
    .then(function (resp) { return resp.json(); })
    .then(function (result) {
        if (!result.success) {
            showToast(result.error || 'Error al procesar', 'error');
            return;
        }

        showSuccessModal(result);
        localStorage.removeItem(MP_CART_KEY);
        updateCartSummaryDisplay();
        updateQtyBadges();
    })
    .catch(function (err) {
        showToast('Error: ' + err.message, 'error');
    });
}

// ===== SHOW SUCCESS MODAL =====
function showSuccessModal(result) {
    currentOrderData = result;

    var modal = document.getElementById('order-success-modal');
    document.getElementById('success-order-number').textContent = result.order_number;
    document.getElementById('success-order-total').textContent = '$' + result.total.toLocaleString('es-CO');

    var desc = document.getElementById('success-modal-description');
    var waBtn = document.getElementById('btn-confirm-whatsapp');
    var backBtn = document.getElementById('btn-volver-menu');

    if (window.isTableOrder) {
        if (desc) desc.innerHTML = 'Tu pedido ha sido enviado a la cocina.<br><strong style="color:#7c3aed;">¡Lo traeremos a tu mesa pronto!</strong>';
        if (waBtn) waBtn.style.display = 'none';
        if (backBtn) {
            backBtn.textContent = 'Volver al Menú';
            backBtn.className = 'mp-btn-confirm-wa';
        }
    } else {
        if (waBtn) waBtn.style.display = 'flex';
    }

    modal.classList.add('visible');
    document.body.style.overflow = 'hidden';
}

// ===== CONFIRM AND REDIRECT WHATSAPP =====
function confirmAndRedirectWhatsApp() {
    if (!currentOrderData) return;
    var msg = 'Hola, soy ' + (currentOrderData.customer_name || 'un cliente') + '. Pedido Nº ' + currentOrderData.order_number + ' realizado. ¿Me confirmas por favor?';
    window.open('https://wa.me/' + window.businessPhone + '?text=' + encodeURIComponent(msg), '_blank');
    location.reload();
}
window.confirmAndRedirectWhatsApp = confirmAndRedirectWhatsApp;

// ===== USE CURRENT LOCATION =====
function useCurrentLocation() {
    if (!navigator.geolocation) {
        showToast('Tu navegador no soporta geolocalización', 'error');
        return;
    }

    var btn = document.getElementById('btn-use-location');
    btn.classList.add('loading');

    navigator.geolocation.getCurrentPosition(
        function (position) {
            var lat = position.coords.latitude;
            var lng = position.coords.longitude;

            fetch('https://nominatim.openstreetmap.org/reverse?format=json&lat=' + lat + '&lon=' + lng + '&addressdetails=1&accept-language=es', {
                headers: { 'User-Agent': 'Orderfox/1.0' }
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var a = data.address || {};
                var parts = [];
                var street = [a.road, a.house_number].filter(Boolean).join(' ');
                if (street) parts.push(street);
                var zone = a.suburb || a.neighbourhood || a.city_district || '';
                var city = a.city || a.town || a.village || a.municipality || '';
                if (zone) parts.push(zone);
                if (city) parts.push(city);
                var addr = parts.join(', ') || data.display_name || '';
                document.getElementById('delivery-address').value = addr;
                showToast('Ubicación obtenida', 'success');
            })
            .catch(function () {
                document.getElementById('delivery-address').value = lat.toFixed(6) + ', ' + lng.toFixed(6);
                showToast('No se pudo obtener la dirección exacta. Revisa el campo.', 'warning');
            })
            .finally(function () {
                btn.classList.remove('loading');
            });
        },
        function (error) {
            var msg = 'Error al obtener ubicación';
            if (error.code === 1) msg = 'Permiso de ubicación denegado';
            else if (error.code === 2) msg = 'Ubicación no disponible';
            else if (error.code === 3) msg = 'Tiempo de espera agotado';
            showToast(msg, 'error');
            btn.classList.remove('loading');
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}
window.useCurrentLocation = useCurrentLocation;

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.openCheckoutModal = openCheckoutModal;
window.actionHandlers.closeAddressModal = closeAddressModal;
window.actionHandlers.processOrderWithAddress = processOrderWithAddress;
window.actionHandlers.confirmAndRedirectWhatsApp = confirmAndRedirectWhatsApp;
window.actionHandlers.useCurrentLocation = useCurrentLocation;

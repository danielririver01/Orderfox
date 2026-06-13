/**
 * cart-core.js - Lógica pura de carrito (localStorage + DOM updates)
 * Dependencias: showToast (definido abajo), closeDetailPanel/detail-panel.js
 */

// ===== TOAST (compatibilidad con mpToast del template) =====
function showToast(message, type = 'info') {
    var toast = document.getElementById('mpToast');
    if (!toast) return;

    toast.textContent = message;
    toast.className = 'mp-toast visible' + (type ? ' ' + type : '');

    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(function () {
        toast.classList.remove('visible');
    }, 3000);
}
window.showToast = showToast;

// ===== CART CONSTANTS =====
var MP_CART_KEY = window.CART_KEY || 'velziaCart_default';
var MP_CART_TTL = 24 * 60 * 60 * 1000;

// ===== LOCALSTORAGE CART =====
function mpLoadCart() {
    try {
        var stored = localStorage.getItem(MP_CART_KEY);
        if (!stored) return {};
        var data = JSON.parse(stored);
        if (data._lastUpdated && (Date.now() - data._lastUpdated > MP_CART_TTL)) {
            localStorage.removeItem(MP_CART_KEY);
            return {};
        }
        return data.items || {};
    } catch (e) {
        return {};
    }
}

function mpSaveCart(cart) {
    localStorage.setItem(MP_CART_KEY, JSON.stringify({
        items: cart,
        _lastUpdated: Date.now()
    }));
}

// ===== CART KEY GENERATOR =====
function makeCartKey(productId, extras) {
    var ids = extras.map(function (e) { return e.id; }).sort();
    return productId + '_' + ids.join('-');
}

// ===== ADD TO ORDER =====
function addDetailToOrder() {
    if (typeof currentDetailProduct === 'undefined' || !currentDetailProduct) return;
    if (!window.menuAvailable) {
        showToast('El menú no está recibiendo pedidos', 'warning');
        return;
    }

    var product = currentDetailProduct;
    var cart = mpLoadCart();
    var cartKey = makeCartKey(product.id, detailSelectedExtras);

    // Modo editar: eliminar entries antiguos de este producto
    if (editMode && editedProductIds.length > 0) {
        editedProductIds.forEach(function (k) {
            delete cart[k];
        });
    }

    // Agregar nuevo entry
    if (cart[cartKey]) {
        cart[cartKey].quantity += detailQuantity;
    } else {
        cart[cartKey] = {
            productId: product.id,
            name: product.name,
            price: product.price,
            quantity: detailQuantity,
            extras: detailSelectedExtras.map(function (e) { return { id: e.id, name: e.name, price: e.price }; }),
            imageUrl: product.image_url
        };
    }

    mpSaveCart(cart);
    updateCartSummaryDisplay();
    updateQtyBadges();
    closeDetailPanel();
    if (editFromCartEditor) {
        editFromCartEditor = false;
        openCartEditor();
    }
    showToast(product.name + (editMode ? ' actualizado' : ' agregado'), 'success');
}
window.addDetailToOrder = addDetailToOrder;

// ===== CANCEL ORDER =====
function cancelOrder() {
    localStorage.removeItem(MP_CART_KEY);
    updateCartSummaryDisplay();
    updateQtyBadges();
    showToast('Pedido cancelado', 'info');
}
window.cancelOrder = cancelOrder;

// ===== CART: Sidebar Summary =====
function updateCartSummaryDisplay() {
    var cart = mpLoadCart();
    var total = 0;
    var count = 0;

    Object.entries(cart).forEach(function (entry) {
        var item = entry[1];
        var extrasTotal = (item.extras || []).reduce(function (sum, e) { return sum + e.price; }, 0);
        total += (item.price + extrasTotal) * item.quantity;
        count += item.quantity;
    });

    var badge = document.getElementById('cartCountBadge');
    var totalEl = document.getElementById('cartSummaryTotal');
    var btn = document.getElementById('btnVerPedido');

    if (badge) badge.textContent = count;
    if (totalEl) totalEl.textContent = '$' + total.toLocaleString('es-CO');
    if (btn) btn.disabled = count === 0;

    var cancelBtn = document.getElementById('btnCancelCart');
    if (cancelBtn) cancelBtn.classList.toggle('hidden', count === 0);

    var editBtn = document.getElementById('btnEditCart');
    if (editBtn) editBtn.classList.toggle('hidden', count === 0);

    // Render items list
    renderCartItems(cart);
}

function renderCartItems(cart) {
    var container = document.getElementById('cartItems');
    if (!container) return;

    var entries = Object.entries(cart);
    if (entries.length === 0) {
        container.innerHTML = '';
        return;
    }

    var html = '';
    entries.forEach(function (entry) {
        var key = entry[0];
        var item = entry[1];
        var extrasTotal = (item.extras || []).reduce(function (sum, e) { return sum + e.price; }, 0);
        var lineTotal = (item.price + extrasTotal) * item.quantity;
        var extrasText = (item.extras || []).map(function (e) { return e.name; }).join(', ');

        html +=
            '<div class="cart-item">' +
            '<div class="cart-item-info">' +
            '<div class="cart-item-name">' + esc(item.name) + '</div>' +
            (extrasText ? '<div class="cart-item-extras">' + esc(extrasText) + '</div>' : '') +
            '</div>' +
            '<span class="cart-item-qty">×' + item.quantity + '</span>' +
            '<span class="cart-item-price">$' + lineTotal.toLocaleString('es-CO') + '</span>' +
            '</div>';
    });

    container.innerHTML = html;
}

function updateQtyBadges() {
    var cart = mpLoadCart();

    document.querySelectorAll('.product-card').forEach(function (card) {
        var productId = card.dataset.id;
        var existing = card.querySelector('.qty-badge-card');
        if (existing) existing.remove();

        // Sumar cantidades de todas las variantes de este producto
        var totalQty = 0;
        Object.entries(cart).forEach(function (entry) {
            var key = entry[0];
            var item = entry[1];
            if (key.startsWith(productId + '_') || key === productId) {
                totalQty += item.quantity;
            }
        });

        if (totalQty > 0) {
            var badge = document.createElement('span');
            badge.className = 'qty-badge-card';
            badge.style.cssText = 'position:absolute;top:0.5rem;left:0.5rem;background:#7c3aed;color:white;font-size:0.7rem;font-weight:800;padding:0.15rem 0.5rem;border-radius:99px;z-index:5;';
            badge.textContent = totalQty;
            var front = card.querySelector('.product-card-front');
            if (front) front.appendChild(badge);
        }

    });
}

// ===== Cross-tab Sync =====
window.addEventListener('storage', function (e) {
    if (e.key === MP_CART_KEY) {
        updateCartSummaryDisplay();
        updateQtyBadges();
    }
});

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.cancelOrder = cancelOrder;
window.actionHandlers.reloadPage = function () { location.reload(); };

/**
 * detail-panel.js - Panel de detalle de producto
 * Dependencias: showToast, closeDetailPanel (ambas accesibles vía window)
 */

// ===== DETAIL STATE =====
var currentDetailProduct = null;
var detailQuantity = 1;
var detailSelectedExtras = [];
var editMode = false;
var editedProductIds = [];
var editFromCartEditor = false;

// ===== UTILS =====
function esc(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ===== OPEN PRODUCT DETAIL =====
function openProductDetail(productId) {
    var card = document.querySelector('.product-card[data-id="' + productId + '"]');
    if (!card) return;

    var product = {
        id: parseInt(card.dataset.id),
        name: card.dataset.name,
        price: parseInt(card.dataset.price),
        description: card.dataset.description || '',
        image_url: null,
        modifiers: []
    };

    // Obtener imagen
    var imgEl = card.querySelector('.product-image-wrap img');
    if (imgEl) product.image_url = imgEl.src;

    // Leer modifiers del data attribute
    try {
        var modsRaw = card.dataset.modifiers;
        if (modsRaw) {
            var mods = JSON.parse(modsRaw);
            product.modifiers = mods.map(function (m) {
                return { id: m.id, name: m.name, extra_price: m.extra_price };
            });
        }
    } catch (e) {
        console.warn('Error parsing modifiers:', e);
    }

    currentDetailProduct = product;

    // Detectar si el producto ya tiene items en carrito → modo editar
    var cart = (typeof mpLoadCart === 'function') ? mpLoadCart() : {};
    var productEntries = [];
    Object.keys(cart).forEach(function (key) {
        if (key.startsWith(productId + '_') || key === productId) {
            productEntries.push({ key: key, item: cart[key] });
        }
    });

    if (productEntries.length > 0) {
        editMode = true;
        editedProductIds = productEntries.map(function (e) { return e.key; });
        var first = productEntries[0].item;
        var totalQty = productEntries.reduce(function (sum, e) { return sum + e.item.quantity; }, 0);
        detailQuantity = totalQty;
        detailSelectedExtras = (first.extras || []).map(function (e) {
            return { id: e.id, name: e.name, price: e.price };
        });
    } else {
        editMode = false;
        editedProductIds = [];
        detailQuantity = 1;
        detailSelectedExtras = [];
    }

    renderDetailPanel(product);
    openDetailPanel();
}
window.openProductDetail = openProductDetail;

// ===== RENDER DETAIL PANEL =====
function renderDetailPanel(product) {
    var body = document.getElementById('detailBody');
    var empty = document.getElementById('detailEmpty');
    var content = document.getElementById('detailContent');

    empty.style.display = 'none';
    content.classList.add('active');

    var imageHTML;
    if (product.image_url) {
        imageHTML = '<div class="detail-image-wrap"><img src="' + esc(product.image_url) + '" alt="' + esc(product.name) + '"></div>';
    } else {
        imageHTML = '<div class="detail-image-wrap"><div class="detail-image-fallback">' + esc(product.name[0]) + '</div></div>';
    }

    var extrasHTML = '';
    if (product.modifiers && product.modifiers.length > 0) {
        var selectedIds = detailSelectedExtras.map(function (e) { return e.id; });
        var items = product.modifiers.map(function (mod) {
            var checked = selectedIds.indexOf(mod.id) !== -1 ? ' checked' : '';
            return '<label class="detail-extra-item' + (checked ? ' checked' : '') + '" data-mod-id="' + mod.id + '">' +
                '<div class="detail-extra-left">' +
                '<input type="checkbox" class="detail-extra-checkbox"' +
                ' data-id="' + mod.id + '" data-name="' + esc(mod.name) + '" data-price="' + mod.extra_price + '"' +
                ' onchange="handleExtraToggle(this)"' + checked + '>' +
                '<span class="detail-extra-name">' + esc(mod.name) + '</span>' +
                '</div>' +
                '<span class="detail-extra-price">+$' + mod.extra_price.toLocaleString('es-CO') + '</span>' +
                '</label>';
        }).join('');

        extrasHTML = '<div class="detail-extras-section">' +
            '<h3 class="detail-extras-title">Extras y modificadores</h3>' +
            items +
            '</div>';
    }

    body.innerHTML =
        imageHTML +
        '<div class="detail-info">' +
        '<h2 class="detail-name">' + esc(product.name) + '</h2>' +
        '<span class="detail-price">$' + product.price.toLocaleString('es-CO') + '</span>' +
        (product.description ? '<p class="detail-description">' + esc(product.description) + '</p>' : '') +
        extrasHTML +
        '<div class="detail-qty-section">' +
        '<button class="btn-qty-detail" data-action="changeDetailQty" data-delta="-1">−</button>' +
        '<span class="qty-display-detail" id="detailQtyDisplay">1</span>' +
        '<button class="btn-qty-detail" data-action="changeDetailQty" data-delta="1">+</button>' +
        '</div>' +
        '</div>' +
        '<div class="detail-footer">' +
        '<div class="detail-total-row">' +
        '<span class="detail-total-label">Total</span>' +
        '<span class="detail-total-value" id="detailTotalValue">$' + product.price.toLocaleString('es-CO') + '</span>' +
        '</div>' +
        '<button class="btn-agregar-pedido" data-action="addDetailToOrder">' +
        (editMode ? 'Actualizar' : 'Agregar al pedido') +
        '</button>' +
        '</div>';
}

// ===== OPEN/CLOSE DETAIL PANEL =====
function openDetailPanel() {
    document.getElementById('detailPanel').classList.add('open');
    var overlay = document.getElementById('detailPanelOverlay');
    if (overlay) overlay.classList.add('active');
    document.getElementById('detailPanel').scrollTop = 0;
}

function closeDetailPanel() {
    document.getElementById('detailPanel').classList.remove('open');
    var overlay = document.getElementById('detailPanelOverlay');
    if (overlay) overlay.classList.remove('active');

    // Resetear contenido
    document.getElementById('detailContent').classList.remove('active');
    document.getElementById('detailEmpty').style.display = '';
    document.getElementById('detailBody').innerHTML = '';

    currentDetailProduct = null;
    detailSelectedExtras = [];
    detailQuantity = 1;
    editMode = false;
    editedProductIds = [];
}
window.closeDetailPanel = closeDetailPanel;

// ===== QUANTITY =====
function changeDetailQty(delta) {
    detailQuantity = Math.max(1, detailQuantity + delta);
    var el = document.getElementById('detailQtyDisplay');
    if (el) el.textContent = detailQuantity;
    updateDetailTotal();
}
window.changeDetailQty = changeDetailQty;

// ===== EXTRAS =====
function handleExtraToggle(checkbox) {
    var id = parseInt(checkbox.dataset.id);
    var name = checkbox.dataset.name;
    var price = parseInt(checkbox.dataset.price);
    var parent = checkbox.closest('.detail-extra-item');

    if (checkbox.checked) {
        detailSelectedExtras.push({ id: id, name: name, price: price });
        if (parent) parent.classList.add('checked');
    } else {
        detailSelectedExtras = detailSelectedExtras.filter(function (e) { return e.id !== id; });
        if (parent) parent.classList.remove('checked');
    }
    updateDetailTotal();
}
window.handleExtraToggle = handleExtraToggle;

// ===== UPDATE TOTAL =====
function updateDetailTotal() {
    if (!currentDetailProduct) return;
    var extrasTotal = detailSelectedExtras.reduce(function (sum, e) { return sum + e.price; }, 0);
    var total = (currentDetailProduct.price + extrasTotal) * detailQuantity;
    var el = document.getElementById('detailTotalValue');
    if (el) el.textContent = '$' + total.toLocaleString('es-CO');
}

// ===== CART EDITOR (carrito completo en panel) =====
function openCartEditor() {
    var cart = (typeof mpLoadCart === 'function') ? mpLoadCart() : {};
    var entries = Object.entries(cart);
    if (entries.length === 0) {
        closeDetailPanel();
        return;
    }

    document.getElementById('detailEmpty').style.display = 'none';
    document.getElementById('detailContent').classList.add('active');
    currentDetailProduct = null;

    // Cache images de los productos
    var productImages = {};
    document.querySelectorAll('.product-card').forEach(function (card) {
        var id = card.dataset.id;
        var img = card.querySelector('.product-image-wrap img');
        if (img) productImages[id] = img.src;
    });

    var body = document.getElementById('detailBody');
    var html = '';
    var grandTotal = 0;

    entries.forEach(function (entry) {
        var key = entry[0];
        var item = entry[1];
        var productId = parseInt(key.split('_')[0]);
        var extrasTotal = (item.extras || []).reduce(function (sum, e) { return sum + e.price; }, 0);
        var lineTotal = (item.price + extrasTotal) * item.quantity;
        grandTotal += lineTotal;
        var extrasText = (item.extras || []).map(function (e) { return e.name; }).join(', ');
        var imgSrc = productImages[productId] || '';

        html +=
            '<div class="cart-editor-item" data-action="editCartEntry" data-key="' + key + '">' +
            (imgSrc
                ? '<div class="cart-editor-img"><img src="' + imgSrc + '" alt="' + esc(item.name) + '"></div>'
                : '<div class="cart-editor-img cart-editor-img-fallback">' + esc(item.name[0]) + '</div>') +
            '<div class="cart-editor-info">' +
            '<div class="cart-editor-name">' + esc(item.name) + '</div>' +
            (extrasText ? '<div class="cart-editor-extras">' + esc(extrasText) + '</div>' : '') +
            '<div class="cart-editor-qty">' +
            '<button class="cart-editor-qty-btn" data-action="cartEditorQty" data-key="' + key + '" data-delta="-1">−</button>' +
            '<span class="cart-editor-qty-val">' + item.quantity + '</span>' +
            '<button class="cart-editor-qty-btn" data-action="cartEditorQty" data-key="' + key + '" data-delta="1">+</button>' +
            '</div>' +
            '</div>' +
            '<div class="cart-editor-price">$' + lineTotal.toLocaleString('es-CO') + '</div>' +
            '</div>';
    });

    html +=
        '<div class="cart-editor-footer">' +
        '<div class="cart-editor-total">' +
        '<span class="cart-editor-total-label">Total</span>' +
        '<span class="cart-editor-total-value">$' + grandTotal.toLocaleString('es-CO') + '</span>' +
        '</div>' +
        '<button class="btn-agregar-pedido" data-action="closeDetailPanel">Actualizar</button>' +
        '</div>';

    body.innerHTML = html;
    openDetailPanel();
}
window.openCartEditor = openCartEditor;

function cartEditorQty(key, delta) {
    var cart = mpLoadCart();
    if (!cart[key]) return;
    cart[key].quantity = Math.max(0, cart[key].quantity + delta);
    if (cart[key].quantity === 0) {
        delete cart[key];
    }
    mpSaveCart(cart);
    updateCartSummaryDisplay();
    updateQtyBadges();
    if (Object.keys(cart).length === 0) {
        closeDetailPanel();
    } else {
        openCartEditor();
    }
}
window.cartEditorQty = cartEditorQty;

// ===== EDITAR ENTRY ESPECÍFICO DESDE CART EDITOR =====
function editCartEntry(cartKey) {
    var cart = (typeof mpLoadCart === 'function') ? mpLoadCart() : {};
    var entry = cart[cartKey];
    if (!entry) return;

    var card = document.querySelector('.product-card[data-id="' + entry.productId + '"]');
    if (!card) return;

    var product = {
        id: parseInt(card.dataset.id),
        name: card.dataset.name,
        price: parseInt(card.dataset.price),
        description: card.dataset.description || '',
        image_url: null,
        modifiers: []
    };

    var imgEl = card.querySelector('.product-image-wrap img');
    if (imgEl) product.image_url = imgEl.src;

    try {
        var modsRaw = card.dataset.modifiers;
        if (modsRaw) {
            var mods = JSON.parse(modsRaw);
            product.modifiers = mods.map(function (m) {
                return { id: m.id, name: m.name, extra_price: m.extra_price };
            });
        }
    } catch (e) {
        console.warn('Error parsing modifiers:', e);
    }

    currentDetailProduct = product;
    editMode = true;
    editFromCartEditor = true;
    editedProductIds = [cartKey];
    detailQuantity = entry.quantity;
    detailSelectedExtras = (entry.extras || []).map(function (e) {
        return { id: e.id, name: e.name, price: e.price };
    });

    renderDetailPanel(product);
    openDetailPanel();
}
window.editCartEntry = editCartEntry;

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.openProductDetail = function (p) { openProductDetail(parseInt(p.id)); };
window.actionHandlers.closeDetailPanel = closeDetailPanel;
window.actionHandlers.changeDetailQty = function (p) { changeDetailQty(parseInt(p.delta)); };
window.actionHandlers.addDetailToOrder = addDetailToOrder;
window.actionHandlers.cartEditorQty = function (p) { cartEditorQty(p.key, parseInt(p.delta)); };
window.actionHandlers.openCartEditor = openCartEditor;
window.actionHandlers.editCartEntry = function (p) { editCartEntry(p.key); };


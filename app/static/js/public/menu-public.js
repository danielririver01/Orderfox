/**
 * menu-public.js - Menú público 3 paneles (autónomo, sin dependencia de cart.js)
 */

// ===== ESTADO GLOBAL =====
let currentDetailProduct = null;
let detailQuantity = 1;
let detailSelectedExtras = [];
let allProductsCache = [];

// ===== CART KEY =====
const MP_CART_KEY = window.CART_KEY || 'velziaCart_default';
const MP_CART_TTL = 24 * 60 * 60 * 1000;

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
    initCategoryNavigation();
    initIntersectionObserver();
    initProductSearch();
    initSidebarSearch();
    cacheAllProducts();
    updateCartSummaryDisplay();
    updateQtyBadges();
    checkDeepLink();
});

// ===== LOCALSTORAGE CART =====
function mpLoadCart() {
    try {
        const stored = localStorage.getItem(MP_CART_KEY);
        if (!stored) return {};
        const data = JSON.parse(stored);
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

// ===== CACHE DE PRODUCTOS =====
function cacheAllProducts() {
    document.querySelectorAll('.product-card').forEach(card => {
        allProductsCache.push({
            id: parseInt(card.dataset.id),
            name: card.dataset.name,
            price: parseInt(card.dataset.price),
            description: card.dataset.description || '',
            keywords: card.dataset.keywords || '',
            element: card
        });
    });
}

// ===== PANEL DE DETALLE =====
function openProductDetail(productId) {
    const card = document.querySelector(`.product-card[data-id="${productId}"]`);
    if (!card) return;

    const product = {
        id: parseInt(card.dataset.id),
        name: card.dataset.name,
        price: parseInt(card.dataset.price),
        description: card.dataset.description || '',
        image_url: card.querySelector('.product-image-wrap img')?.src || null,
        modifiers: []
    };

    // Leer modifiers del data attribute
    try {
        const modsRaw = card.dataset.modifiers;
        if (modsRaw) {
            const mods = JSON.parse(modsRaw);
            product.modifiers = mods.map(m => ({
                id: m.id,
                name: m.name,
                extra_price: m.extra_price
            }));
        }
    } catch (e) {
        console.warn('Error parsing modifiers:', e);
    }

    currentDetailProduct = product;
    detailQuantity = 1;
    detailSelectedExtras = [];

    renderDetailPanel(product);
    openDetailPanel();
}
window.openProductDetail = openProductDetail;

function renderDetailPanel(product) {
    const body = document.getElementById('detailBody');
    const empty = document.getElementById('detailEmpty');
    const content = document.getElementById('detailContent');

    empty.style.display = 'none';
    content.classList.add('active');

    let imageHTML;
    if (product.image_url) {
        imageHTML = `<div class="detail-image-wrap"><img src="${esc(product.image_url)}" alt="${esc(product.name)}"></div>`;
    } else {
        imageHTML = `<div class="detail-image-wrap"><div class="detail-image-fallback">${esc(product.name[0])}</div></div>`;
    }

    let extrasHTML = '';
    if (product.modifiers && product.modifiers.length > 0) {
        const items = product.modifiers.map(mod => `
            <label class="detail-extra-item" data-mod-id="${mod.id}">
                <div class="detail-extra-left">
                    <input type="checkbox" class="detail-extra-checkbox"
                        data-id="${mod.id}" data-name="${esc(mod.name)}" data-price="${mod.extra_price}"
                        onchange="handleExtraToggle(this)">
                    <span class="detail-extra-name">${esc(mod.name)}</span>
                </div>
                <span class="detail-extra-price">+$${mod.extra_price.toLocaleString('es-CO')}</span>
            </label>
        `).join('');

        extrasHTML = `
            <div class="detail-extras-section">
                <h3 class="detail-extras-title">Extras y modificadores</h3>
                ${items}
            </div>
        `;
    }

    body.innerHTML = `
        ${imageHTML}
        <div class="detail-info">
            <h2 class="detail-name">${esc(product.name)}</h2>
            <span class="detail-price">$${product.price.toLocaleString('es-CO')}</span>
            ${product.description ? `<p class="detail-description">${esc(product.description)}</p>` : ''}
            ${extrasHTML}
            <div class="detail-qty-section">
                <button class="btn-qty-detail" onclick="changeDetailQty(-1)">−</button>
                <span class="qty-display-detail" id="detailQtyDisplay">1</span>
                <button class="btn-qty-detail" onclick="changeDetailQty(1)">+</button>
            </div>
        </div>
        <div class="detail-footer">
            <div class="detail-total-row">
                <span class="detail-total-label">Total</span>
                <span class="detail-total-value" id="detailTotalValue">$${product.price.toLocaleString('es-CO')}</span>
            </div>
            <button class="btn-agregar-pedido" onclick="addDetailToOrder()">
                Agregar al pedido
            </button>
        </div>
    `;
}

function openDetailPanel() {
    document.getElementById('detailPanel').classList.add('open');
    const overlay = document.getElementById('detailPanelOverlay');
    if (overlay) overlay.classList.add('active');
    document.getElementById('detailPanel').scrollTop = 0;
}

function closeDetailPanel() {
    document.getElementById('detailPanel').classList.remove('open');
    const overlay = document.getElementById('detailPanelOverlay');
    if (overlay) overlay.classList.remove('active');

    // Resetear contenido
    document.getElementById('detailContent').classList.remove('active');
    document.getElementById('detailEmpty').style.display = '';
    document.getElementById('detailBody').innerHTML = '';

    currentDetailProduct = null;
    detailSelectedExtras = [];
    detailQuantity = 1;
}
window.closeDetailPanel = closeDetailPanel;

// ===== CANTIDAD =====
function changeDetailQty(delta) {
    detailQuantity = Math.max(1, detailQuantity + delta);
    const el = document.getElementById('detailQtyDisplay');
    if (el) el.textContent = detailQuantity;
    updateDetailTotal();
}
window.changeDetailQty = changeDetailQty;

// ===== EXTRAS =====
function handleExtraToggle(checkbox) {
    const id = parseInt(checkbox.dataset.id);
    const name = checkbox.dataset.name;
    const price = parseInt(checkbox.dataset.price);
    const parent = checkbox.closest('.detail-extra-item');

    if (checkbox.checked) {
        detailSelectedExtras.push({ id, name, price });
        if (parent) parent.classList.add('checked');
    } else {
        detailSelectedExtras = detailSelectedExtras.filter(e => e.id !== id);
        if (parent) parent.classList.remove('checked');
    }
    updateDetailTotal();
}
window.handleExtraToggle = handleExtraToggle;

function updateDetailTotal() {
    if (!currentDetailProduct) return;
    const extrasTotal = detailSelectedExtras.reduce((sum, e) => sum + e.price, 0);
    const total = (currentDetailProduct.price + extrasTotal) * detailQuantity;
    const el = document.getElementById('detailTotalValue');
    if (el) el.textContent = `$${total.toLocaleString('es-CO')}`;
}

// ===== AGREGAR AL PEDIDO =====
function makeCartKey(productId, extras) {
    const ids = extras.map(e => e.id).sort();
    return productId + '_' + ids.join('-');
}

function addDetailToOrder() {
    if (!currentDetailProduct) return;
    if (!window.menuAvailable) {
        toast('El menú no está recibiendo pedidos', 'warning');
        return;
    }

    const product = currentDetailProduct;
    const cart = mpLoadCart();
    const cartKey = makeCartKey(product.id, detailSelectedExtras);

    // Buscar si ya existe con los mismos extras
    if (cart[cartKey]) {
        cart[cartKey].quantity += detailQuantity;
    } else {
        cart[cartKey] = {
            productId: product.id,
            name: product.name,
            price: product.price,
            quantity: detailQuantity,
            extras: detailSelectedExtras.map(e => ({ id: e.id, name: e.name, price: e.price })),
            imageUrl: product.image_url
        };
    }

    mpSaveCart(cart);
    updateCartSummaryDisplay();
    updateQtyBadges();
    closeDetailPanel();
    toast(`${product.name} agregado`, 'success');
}
window.addDetailToOrder = addDetailToOrder;

// ===== CANCELAR PEDIDO =====
function cancelOrder() {
    localStorage.removeItem(MP_CART_KEY);
    updateCartSummaryDisplay();
    updateQtyBadges();
    toast('Pedido cancelado', 'info');
}
window.cancelOrder = cancelOrder;

// ===== CARRITO: Resumen en Sidebar =====
function updateCartSummaryDisplay() {
    const cart = mpLoadCart();
    let total = 0;
    let count = 0;

    Object.entries(cart).forEach(([id, item]) => {
        const extrasTotal = (item.extras || []).reduce((sum, e) => sum + e.price, 0);
        total += (item.price + extrasTotal) * item.quantity;
        count += item.quantity;
    });

    const badge = document.getElementById('cartCountBadge');
    const totalEl = document.getElementById('cartSummaryTotal');
    const btn = document.getElementById('btnVerPedido');
    const cancelBtn = document.getElementById('btnCancelCart');

    if (badge) badge.textContent = count;
    if (totalEl) totalEl.textContent = `$${total.toLocaleString('es-CO')}`;
    if (btn) btn.disabled = count === 0;
    if (cancelBtn) cancelBtn.classList.toggle('hidden', count === 0);
}

function updateQtyBadges() {
    const cart = mpLoadCart();

    document.querySelectorAll('.product-card').forEach(card => {
        const productId = card.dataset.id;
        const existing = card.querySelector('.qty-badge-card');
        if (existing) existing.remove();

        // Sumar cantidades de todas las variantes de este producto
        let totalQty = 0;
        Object.entries(cart).forEach(([key, item]) => {
            if (key.startsWith(productId + '_') || key === productId) {
                totalQty += item.quantity;
            }
        });

        if (totalQty > 0) {
            const badge = document.createElement('span');
            badge.className = 'qty-badge-card';
            badge.style.cssText = 'position:absolute;top:0.5rem;left:0.5rem;background:#7c3aed;color:white;font-size:0.7rem;font-weight:800;padding:0.15rem 0.5rem;border-radius:99px;z-index:5;';
            badge.textContent = totalQty;
            const front = card.querySelector('.product-card-front');
            if (front) front.appendChild(badge);
        }
    });
}

// Sync cross-tab
window.addEventListener('storage', (e) => {
    if (e.key === MP_CART_KEY) {
        updateCartSummaryDisplay();
        updateQtyBadges();
    }
});

// ===== NAVEGACIÓN POR CATEGORÍAS =====
function initCategoryNavigation() {
    document.querySelectorAll('.category-item').forEach(item => {
        item.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            const target = document.getElementById(targetId);
            if (target) {
                const area = document.getElementById('productsArea');
                area.scrollTo({ top: target.offsetTop - 80, behavior: 'smooth' });
            }
            if (window.innerWidth <= 768) closeSidebar();
        });
    });
}

// ===== INTERSECTION OBSERVER =====
function initIntersectionObserver() {
    const sections = document.querySelectorAll('.category-section');
    if (!sections.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const catId = entry.target.dataset.categoryId;
                setActiveCategory(catId);
                const title = entry.target.querySelector('.category-section-title');
                const headerTitle = document.getElementById('currentCategoryTitle');
                if (title && headerTitle) headerTitle.textContent = title.textContent;
            }
        });
    }, {
        root: document.getElementById('productsArea'),
        rootMargin: '-20% 0px -60% 0px',
        threshold: 0
    });

    sections.forEach(s => observer.observe(s));
}

function setActiveCategory(catId) {
    document.querySelectorAll('.category-item').forEach(item => {
        item.classList.toggle('active', item.dataset.categoryId === catId);
    });
    const active = document.querySelector(`.category-item[data-category-id="${catId}"]`);
    if (active) active.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ===== BÚSQUEDA DE PRODUCTOS =====
function initProductSearch() {
    const input = document.getElementById('productSearch');
    if (!input) return;

    let timer;
    input.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(() => searchProducts(this.value.trim().toLowerCase()), 200);
    });
}

function searchProducts(term) {
    const noResults = document.getElementById('noSearchResults');
    let found = 0;

    document.querySelectorAll('.product-card').forEach(card => {
        const kw = card.dataset.keywords || '';
        const name = card.dataset.name?.toLowerCase() || '';
        const match = term === '' || kw.includes(term) || name.includes(term);
        card.style.display = match ? '' : 'none';
        if (match) found++;
    });

    document.querySelectorAll('.category-section').forEach(section => {
        const visible = section.querySelectorAll('.product-card:not([style*="display: none"])');
        section.style.display = (visible.length === 0 && term !== '') ? 'none' : '';
    });

    if (noResults) noResults.classList.toggle('visible', found === 0 && term !== '');
}

// ===== BÚSQUEDA DE CATEGORÍAS =====
function initSidebarSearch() {
    const input = document.getElementById('sidebarSearch');
    if (!input) return;

    input.addEventListener('input', function () {
        const term = this.value.trim().toLowerCase();
        document.querySelectorAll('.category-item').forEach(item => {
            const name = item.querySelector('.cat-name')?.textContent.toLowerCase() || '';
            item.style.display = (term === '' || name.includes(term)) ? '' : 'none';
        });
    });
}

// ===== MOBILE SIDEBAR =====
function toggleSidebar() {
    document.getElementById('sidebarLeft').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('active');
}
window.toggleSidebar = toggleSidebar;

function closeSidebar() {
    document.getElementById('sidebarLeft').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('active');
}

// ===== CHECKOUT =====
function openCheckoutModal() {
    const cart = mpLoadCart();
    if (Object.keys(cart).length === 0) {
        toast('Agrega productos al pedido primero', 'warning');
        return;
    }

    // Anti-bot
    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const headers = { 'Content-Type': 'application/json' };
    if (csrf) headers['X-CSRFToken'] = csrf;
    fetch('/menu/api/init-checkout', { method: 'POST', headers, body: JSON.stringify({ restaurant_id: window.restaurantId }) });

    document.getElementById('address-modal').classList.add('visible');
    document.body.style.overflow = 'hidden';
}
window.openCheckoutModal = openCheckoutModal;

function closeAddressModal() {
    document.getElementById('address-modal').classList.remove('visible');
    document.body.style.overflow = '';
}
window.closeAddressModal = closeAddressModal;

function processOrderWithAddress() {
    const fields = {
        'delivery-name': 'Nombre',
        'delivery-phone': 'Teléfono',
        'delivery-address': 'Dirección'
    };

    let hasError = false;
    const values = {};

    Object.keys(fields).forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        let val = el.value.trim();
        if (id === 'delivery-phone') val = val.replace(/[-\s]/g, '');
        values[id] = val;

        let isValid = val !== '';
        if (id === 'delivery-phone' && val) {
            isValid = /^3\d{9}$/.test(val);
            if (!isValid) toast('El teléfono debe tener 10 dígitos y empezar con 3', 'error');
        }
        if (!isValid) {
            hasError = true;
            el.style.borderColor = '#ef4444';
            setTimeout(() => { el.style.borderColor = ''; }, 3000);
        }
    });

    if (hasError) { toast('Faltan datos requeridos', 'warning'); return; }

    closeAddressModal();
    performCheckout(values['delivery-address'], values['delivery-name'], values['delivery-phone']);
}
window.processOrderWithAddress = processOrderWithAddress;

async function performCheckout(address, customerName, phone) {
    const cart = mpLoadCart();

    try {
        // Transformar carrito: el backend espera product_id como key
        const serverCart = {};
        let total = 0;
        for (const key in cart) {
            const item = cart[key];
            const pid = item.productId || parseInt(key.split('_')[0]);
            const extrasTotal = (item.extras || []).reduce((s, e) => s + e.price, 0);
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

        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const headers = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRFToken'] = csrf;

        const resp = await fetch('/menu/api/order', {
            method: 'POST',
            headers,
            body: JSON.stringify({
                cart: serverCart,
                total,
                restaurant_id: window.restaurantId,
                address,
                customer_name: customerName,
                customer_phone: phone,
                user_secondary_email: ''
            })
        });

        const result = await resp.json();

        if (!result.success) {
            toast(result.error || 'Error al procesar', 'error');
            return;
        }

        showSuccessModal(result);
        localStorage.removeItem(MP_CART_KEY);
        updateCartSummaryDisplay();
        updateQtyBadges();

    } catch (err) {
        toast('Error: ' + err.message, 'error');
    }
}

let currentOrderData = null;

function showSuccessModal(result) {
    currentOrderData = result;

    const modal = document.getElementById('order-success-modal');
    document.getElementById('success-order-number').textContent = result.order_number;
    document.getElementById('success-order-total').textContent = `$${result.total.toLocaleString('es-CO')}`;

    const desc = document.getElementById('success-modal-description');
    const waBtn = document.getElementById('btn-confirm-whatsapp');
    const backBtn = document.getElementById('btn-volver-menu');

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

function confirmAndRedirectWhatsApp() {
    if (!currentOrderData) return;
    const msg = `Hola, soy ${currentOrderData.customer_name || 'un cliente'}. Pedido Nº ${currentOrderData.order_number} realizado. ¿Me confirmas por favor?`;
    window.open(`https://wa.me/${window.businessPhone}?text=${encodeURIComponent(msg)}`, '_blank');
    location.reload();
}
window.confirmAndRedirectWhatsApp = confirmAndRedirectWhatsApp;

// ===== 3D FLIP CARDS =====
function flipCard(productId) {
    const card = document.querySelector(`.product-card[data-id="${productId}"]`);
    if (!card) return;
    card.classList.toggle('flipped');
    if (card.classList.contains('flipped')) loadQR(productId);
}
window.flipCard = flipCard;

function loadQR(productId) {
    const img = document.getElementById(`qr-${productId}`);
    if (!img || img.dataset.loaded === 'true') return;
    const url = `${window.location.origin}${window.location.pathname}#product-${productId}`;
    img.onload = () => {
        img.style.display = 'block';
        const loader = img.previousElementSibling;
        if (loader) loader.style.display = 'none';
        img.dataset.loaded = 'true';
    };
    img.src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;
}

// ===== SHARE =====
async function shareProduct(productId, productName, categoryName) {
    const url = `${window.location.origin}${window.location.pathname}#product-${productId}`;
    try {
        if (navigator.share) {
            await navigator.share({ title: productName, text: `¡Prueba ${productName}!`, url });
        } else {
            await navigator.clipboard.writeText(url);
            toast('¡Enlace copiado!', 'success');
        }
    } catch (e) {}
}
window.shareProduct = shareProduct;

// ===== DEEP LINK =====
function checkDeepLink() {
    const hash = window.location.hash;
    if (hash && hash.startsWith('#product-')) {
        const id = hash.split('-')[1];
        const card = document.querySelector(`.product-card[data-id="${id}"]`);
        if (card) {
            setTimeout(() => {
                card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                card.style.borderColor = '#7c3aed';
                card.style.boxShadow = '0 0 0 2px rgba(124,58,237,0.4)';
                setTimeout(() => { card.style.borderColor = ''; card.style.boxShadow = ''; }, 2500);
            }, 500);
        }
    }
}

// ===== TOAST =====
function toast(message, type) {
    const el = document.getElementById('mpToast');
    if (!el) return;
    el.textContent = message;
    el.className = 'mp-toast visible ' + (type || '');
    setTimeout(() => el.classList.remove('visible'), 3000);
}
window.toast = toast;

// ===== UTILS =====
function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

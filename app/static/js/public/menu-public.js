/**
 * menu-public.js - Orquestador: init, navegación por categorías, búsqueda, sidebar
 *
 * Carga DESPUÉS de: interactions.js, cart-core.js, detail-panel.js, checkout.js
 * Funciones eliminadas (duplicadas con interactions.js): flipCard, loadQR, shareProduct, checkDeepLink, esc
 * Funciones eliminadas (extraídas): todas las de cart, detail-panel, checkout
 */

// ===== PRODUCT CACHE =====
var allProductsCache = [];

// ===== INIT =====
document.addEventListener('DOMContentLoaded', function () {
    initCategoryNavigation();
    initIntersectionObserver();
    initProductSearch();
    initSidebarSearch();
    cacheAllProducts();
    updateCartSummaryDisplay();
    updateQtyBadges();
});

// ===== CACHE DE PRODUCTOS =====
function cacheAllProducts() {
    document.querySelectorAll('.product-card').forEach(function (card) {
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

// ===== NAVEGACIÓN POR CATEGORÍAS =====
function initCategoryNavigation() {
    document.querySelectorAll('.category-item').forEach(function (item) {
        item.addEventListener('click', function (e) {
            e.preventDefault();
            var targetId = this.getAttribute('href').substring(1);
            var target = document.getElementById(targetId);
            if (target) {
                var area = document.getElementById('productsArea');
                area.scrollTo({ top: target.offsetTop - 80, behavior: 'smooth' });
            }
            if (window.innerWidth <= 768) closeSidebar();
        });
    });
}

// ===== INTERSECTION OBSERVER =====
function initIntersectionObserver() {
    var sections = document.querySelectorAll('.category-section');
    if (!sections.length) return;

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                var catId = entry.target.dataset.categoryId;
                setActiveCategory(catId);
                var title = entry.target.querySelector('.category-section-title');
                var headerTitle = document.getElementById('currentCategoryTitle');
                if (title && headerTitle) headerTitle.textContent = title.textContent;
            }
        });
    }, {
        root: document.getElementById('productsArea'),
        rootMargin: '-20% 0px -60% 0px',
        threshold: 0
    });

    sections.forEach(function (s) { observer.observe(s); });
}

function setActiveCategory(catId) {
    document.querySelectorAll('.category-item').forEach(function (item) {
        item.classList.toggle('active', item.dataset.categoryId === catId);
    });
    var active = document.querySelector('.category-item[data-category-id="' + catId + '"]');
    if (active) active.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ===== BÚSQUEDA DE PRODUCTOS =====
function initProductSearch() {
    var input = document.getElementById('productSearch');
    if (!input) return;

    var timer;
    input.addEventListener('input', function () {
        clearTimeout(timer);
        var self = this;
        timer = setTimeout(function () { searchProducts(self.value.trim().toLowerCase()); }, 200);
    });
}

function searchProducts(term) {
    var noResults = document.getElementById('noSearchResults');
    var found = 0;

    document.querySelectorAll('.product-card').forEach(function (card) {
        var kw = card.dataset.keywords || '';
        var name = (card.dataset.name || '').toLowerCase();
        var match = term === '' || kw.includes(term) || name.includes(term);
        card.style.display = match ? '' : 'none';
        if (match) found++;
    });

    document.querySelectorAll('.category-section').forEach(function (section) {
        var visible = section.querySelectorAll('.product-card:not([style*="display: none"])');
        section.style.display = (visible.length === 0 && term !== '') ? 'none' : '';
    });

    if (noResults) noResults.classList.toggle('visible', found === 0 && term !== '');
}

// ===== BÚSQUEDA DE CATEGORÍAS =====
function initSidebarSearch() {
    var input = document.getElementById('sidebarSearch');
    if (!input) return;

    input.addEventListener('input', function () {
        var term = this.value.trim().toLowerCase();
        document.querySelectorAll('.category-item').forEach(function (item) {
            var nameEl = item.querySelector('.cat-name');
            var name = nameEl ? nameEl.textContent.toLowerCase() : '';
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

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.toggleSidebar = toggleSidebar;

let currentPage = 1;
let searchQuery = '';
let hasNextPage = false;
const cart = {}; // product_id -> quantity
const productPrices = {}; // product_id -> price

// Elementos del DOM
const productListItems = document.getElementById('product-list-items');
const productSkeleton = document.getElementById('product-skeleton');
const emptyState = document.getElementById('empty-state');
const loadMoreBtn = document.getElementById('load-more-btn');
const loadMoreContainer = document.getElementById('load-more-container');
const searchInput = document.getElementById('product-search');
const orderTotal = document.getElementById('order-total');
const itemsJsonInput = document.getElementById('items-json');
const noResultsMessage = document.getElementById('no-results-message');

async function fetchProducts(page = 1, query = '', append = false) {
    if (!append) {
        productListItems.innerHTML = '';
        currentPage = 1;
    }

    productSkeleton.classList.remove('hidden');
    emptyState.classList.add('hidden');
    loadMoreContainer.classList.add('hidden');
    noResultsMessage.classList.add('hidden');

    try {
        const response = await fetch(`/products/search?q=${encodeURIComponent(query)}&page=${page}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();

        productSkeleton.classList.add('hidden');

        if (data.products.length === 0 && !append) {
            emptyState.classList.remove('hidden');
            return;
        }

        data.products.forEach(product => {
            // Guardar precio en caché para cálculos posteriores aunque el item no esté en el DOM
            productPrices[product.id.toString()] = product.price;

            const itemHtml = createProductItemHtml(product);
            productListItems.insertAdjacentHTML('beforeend', itemHtml);
        });

        hasNextPage = data.has_next;
        currentPage = data.page;

        if (hasNextPage) {
            loadMoreContainer.classList.remove('hidden');
        }

    } catch (error) {
        console.error('Error fetching products:', error);
        productSkeleton.classList.add('hidden');
        if (!append) {
             emptyState.classList.remove('hidden');
        }
    }
}

function createProductItemHtml(product) {
    const qty = cart[product.id.toString()] || 0;
    return `
        <div class="product-item flex items-center justify-between py-3 border-b border-gray-50 dark:border-[#262626] last:border-0" data-id="${product.id}" data-price="${product.price}">
            <div class="flex-1 min-w-0 pr-4">
                <h3 class="product-name font-bold text-gray-900 dark:text-white tracking-tight truncate">${product.name}</h3>
                <p class="text-sm font-black text-[#f2460d]">${product.price_formatted}</p>
            </div>
            <div class="flex items-center gap-4">
                <button type="button" onclick="updateQty('${product.id}', -1)" class="w-9 h-9 rounded-xl bg-gray-50 dark:bg-[#0a0a0a] border border-gray-100 dark:border-[#262626] flex items-center justify-center text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-all active:scale-90">
                    <span class="material-symbols-outlined text-[18px]">remove</span>
                </button>
                <span id="qty-${product.id}" class="w-6 text-center font-black dark:text-white">${qty}</span>
                <button type="button" onclick="updateQty('${product.id}', 1)" class="w-9 h-9 rounded-xl bg-gray-50 dark:bg-[#0a0a0a] border border-gray-100 dark:border-[#262626] flex items-center justify-center text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-all active:scale-90">
                    <span class="material-symbols-outlined text-[18px]">add</span>
                </button>
            </div>
        </div>
    `;
}

function updateQty(productId, delta) {
    productId = productId.toString();
    let currentQty = cart[productId] || 0;
    currentQty = Math.max(0, currentQty + delta);

    const qtySpan = document.getElementById(`qty-${productId}`);
    if (qtySpan) {
        qtySpan.textContent = currentQty;
    }

    if (currentQty > 0) {
        cart[productId] = currentQty;
    } else {
        delete cart[productId];
    }

    calculateTotal();
}

function calculateTotal() {
    let total = 0;
    const items = [];

    for (const [id, qty] of Object.entries(cart)) {
        const price = productPrices[id] || 0;
        total += price * qty;
        items.push({
            product_id: parseInt(id),
            quantity: qty
        });
    }

    orderTotal.textContent = '$' + total.toLocaleString();
    itemsJsonInput.value = JSON.stringify(items);
}

// Hacer globales para los atributos onclick de los botones
window.updateQty = updateQty;

// Debounce search
let timeout = null;
if (searchInput) {
    searchInput.addEventListener('input', (e) => {
        clearTimeout(timeout);
        searchQuery = e.target.value.trim();
        timeout = setTimeout(() => {
            fetchProducts(1, searchQuery, false);
        }, 400);
    });
}

if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
        if (hasNextPage) {
            fetchProducts(currentPage + 1, searchQuery, true);
        }
    });
}

// Inicializar
document.addEventListener('DOMContentLoaded', () => {
    fetchProducts();

    const orderForm = document.getElementById('order-form');
    if (orderForm) {
        orderForm.onsubmit = function(e) {
            const items = JSON.parse(itemsJsonInput.value || '[]');
            if (items.length === 0) {
                e.preventDefault();
                showToast('Por favor selecciona al menos un producto', 'error');
                
                const productSection = document.getElementById('product-list-container');
                if (productSection) {
                    productSection.classList.add('ring-2', 'ring-red-200');
                    setTimeout(() => productSection.classList.remove('ring-2', 'ring-red-200'), 500);
                }
            }
        };
    }
});

// Función para mostrar Toast Notifications
function showToast(message, type = 'error') {
    const container = document.getElementById('toast-container');
    if (!container) {
        alert(message);
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let iconSvg = '';
    if (type === 'success') {
        iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`;
    } else {
        iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>`;
    }

    toast.innerHTML = `
        ${iconSvg}
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

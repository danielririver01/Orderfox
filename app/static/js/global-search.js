// ============================================
// SISTEMA DE BÚSQUEDA GLOBAL - VELZIA (FIXED)
// ============================================

const searchInput = document.getElementById('productSearch');
const clearBtn = document.getElementById('clearSearch');
const noResults = document.getElementById('noResults');
const productGrid = document.getElementById('productGrid');

let allProducts = []; // Aquí guardaremos el menú completo del servidor

document.addEventListener('DOMContentLoaded', function() {
    loadAllProducts();
});

// 1. Cargar todos los productos del restaurante al iniciar
async function loadAllProducts() {
    try {
        const slug = window.restaurantSlug;
        if (!slug) return;
        
        const response = await fetch(`/menu/${slug}/search-products`);
        const data = await response.json();
        
        if (data.success) {
            allProducts = data.products || [];
        }
    } catch (error) {
        console.error('Error en fetch global:', error);
    }
    
}

// 2. Lógica de búsqueda en tiempo real
if (searchInput) {
    searchInput.addEventListener('input', function(e) {
        const term = e.target.value.toLowerCase().trim();
        
        // Control del botón "X"
        if (clearBtn) clearBtn.style.display = term !== '' ? 'flex' : 'none';

        if (term === '') {
            resetSearch();
            return;
        }

        performSearch(term);
    });
}

function performSearch(term) {
    // Primero, eliminamos cualquier tarjeta "global" inyectada anteriormente
    document.querySelectorAll('.global-result').forEach(el => el.remove());

    let foundCount = 0;

    // A. Filtrar productos que YA están físicamente en el HTML (Categoría actual)
    const localCards = document.querySelectorAll('.product-card:not(.global-result)');
    localCards.forEach(card => {
        const name = card.dataset.name.toLowerCase();
        const desc = card.dataset.description.toLowerCase();
        
        if (name.includes(term) || desc.includes(term)) {
            card.style.display = 'block';
            foundCount++;
        } else {
            card.style.display = 'none';
        }
    });

    // B. Buscar en el resto del menú (Los que NO están en el HTML)
    const globalMatches = allProducts.filter(p => {
        const alreadyInDom = document.querySelector(`.product-card[data-id="${p.id}"]`);
        const matches = p.name.toLowerCase().includes(term) || (p.description && p.description.toLowerCase().includes(term));
        return matches && !alreadyInDom;
    });

    globalMatches.forEach(product => {
        const newCard = createGlobalProductCard(product);
        productGrid.appendChild(newCard);
        foundCount++;
    });

    // C. Mostrar mensaje si no hay nada de nada
    noResults.style.display = foundCount === 0 ? 'block' : 'none';
}

// 3. Generador de tarjetas dinámicas (reproduce fielmente tu Jinja)
function createGlobalProductCard(product) {
    const article = document.createElement('article');
    article.className = 'product-card global-result'; // Clase especial para borrarla luego
    article.dataset.id = product.id;
    article.dataset.name = product.name;
    
    // Le ponemos un distintivo para que el usuario sepa que es de otra categoría
    const badge = `<div style="font-size: 0.7rem; background: #f3f4f6; color: #666; padding: 2px 8px; border-radius: 10px; width: fit-content; margin-bottom: 5px;">Sección: ${product.category_name}</div>`;

    article.innerHTML = `
        ${badge}
        <div class="product-header">
            <h3 class="product-name">${product.name}</h3>
            <span class="product-price">$${product.price.toLocaleString()}</span>
        </div>
        <p class="product-description" style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1rem;">
            ${product.description || 'Deliciosa preparación con ingredientes de calidad.'}
        </p>
        <div class="quantity-controls">
            <button class="btn-qty" onclick="updateQty(${product.id}, -1)">-</button>
            <span class="qty-display" id="qty-${product.id}">0</span>
            <button class="btn-qty" onclick="updateQty(${product.id}, 1)">+</button>
        </div>
    `;

    // Sincronizar cantidad si ya está en el carrito (si tienes esa función global)
    if (typeof syncQtyDisplay === 'function') syncQtyDisplay(product.id);

    return article;
}

// 4. Resetear todo al estado original
function resetSearch() {
    document.querySelectorAll('.global-result').forEach(el => el.remove());
    document.querySelectorAll('.product-card').forEach(card => card.style.display = 'block');
    noResults.style.display = 'none';
    if (clearBtn) clearBtn.style.display = 'none';
}

function clearSearch() {
    searchInput.value = '';
    resetSearch();
    searchInput.focus();
}

window.clearSearch = clearSearch;
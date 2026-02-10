async function toggleProduct(id, newState) {
    try {
        const response = await fetch(`/products/${id}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: newState })
        });
        const result = await response.json();
        if (!response.ok) {
            const checkbox = document.querySelector(`[data-product-id="${id}"] input[type="checkbox"]`);
            if (checkbox) checkbox.checked = !newState;
            showToast(result.message || result.error || 'Error al cambiar el producto');
            return;
        }
        if (!result.success) {
            const checkbox = document.querySelector(`[data-product-id="${id}"] input[type="checkbox"]`);
            if (checkbox) checkbox.checked = !newState;
            showToast(result.message || 'Error al cambiar el producto');
        }
    } catch (error) {
        const checkbox = document.querySelector(`[data-product-id="${id}"] input[type="checkbox"]`);
        if (checkbox) checkbox.checked = !newState;
        showToast('Error de conexión');
    }
}

function showToast(message) {
    const toast = document.getElementById('toast');
    if (toast) {
        const messageEl = document.getElementById('toast-message');
        if (messageEl) messageEl.textContent = message;
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 3000);
    }
}

// Search and UI Functionality
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const clearBtn = document.getElementById('clear-search');
    const productCards = document.querySelectorAll('.product-card');
    const noResults = document.getElementById('no-results');
    const categoryTitles = document.querySelectorAll('.category-title');
    const messages = document.querySelectorAll('.flash-message');

    // 1. Live Search
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase().trim();
            
            if (clearBtn) {
                clearBtn.classList.toggle('hidden', term === '');
            }

            let visibleCount = 0;

            productCards.forEach(card => {
                const name = card.dataset.name || "";
                
                if (name.includes(term)) {
                    card.style.display = 'block';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            // Update category titles visibility
            categoryTitles.forEach(title => {
                let hasVisibleProducts = false;
                let nextElement = title.nextElementSibling;
                
                while (nextElement && !nextElement.classList.contains('category-title')) {
                    if (nextElement.classList.contains('product-card') && nextElement.style.display !== 'none') {
                        hasVisibleProducts = true;
                        break;
                    }
                    nextElement = nextElement.nextElementSibling;
                }
                title.style.display = hasVisibleProducts ? 'block' : 'none';
            });

            if (noResults) {
                noResults.classList.toggle('hidden', visibleCount > 0 || term === '');
            }
        });
    }

    // 2. Clear Search
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            searchInput.value = '';
            searchInput.dispatchEvent(new Event('input'));
            searchInput.focus();
        });
    }

    // 3. Auto-hide flash messages
    messages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transition = 'opacity 0.5s ease';
            setTimeout(() => msg.remove(), 500);
        }, 5000);
    });
});
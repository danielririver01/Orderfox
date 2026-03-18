/**
 * Products Management - Velzia
 */

// Toggle Product Status
async function toggleProduct(id, newState) {
    try {
        const response = await fetch(`/products/${id}/toggle`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_active: newState })
        });
        
        if (!response.ok) throw new Error('Error al actualizar');
        
        showToast(newState ? 'Producto activado' : 'Producto desactivado');
        
    } catch (error) {
        // Rollback
        const checkbox = document.querySelector(`[data-product-id="${id}"] input[type="checkbox"]`);
        if (checkbox) checkbox.checked = !newState;
        showToast('Error de conexión. Intenta de nuevo.');
    }
}


// Close Delete Modal
function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    }
}

// Show Toast Notification
function showToast(message) {
    const toast = document.getElementById('toast');
    if (toast) {
        const messageEl = document.getElementById('toast-message');
        if (messageEl) messageEl.textContent = message;
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 3000);
    }
}

// Live Search Functionality
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const productCards = document.querySelectorAll('.product-card');
    const noResults = document.getElementById('no-results');
    const messages = document.querySelectorAll('.flash-message');

    // 1. Live Search
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase().trim();
            let visibleCount = 0;

            productCards.forEach(card => {
                const name = card.dataset.name?.toLowerCase() || "";
                const description = card.dataset.description?.toLowerCase() || "";
                
                if (name.includes(term) || description.includes(term)) {
                    card.style.display = 'block';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            if (noResults) {
                noResults.classList.toggle('hidden', visibleCount > 0 || term === '');
            }
        });
    }

    // 2. Auto-hide flash messages
    messages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transition = 'opacity 0.5s ease';
            setTimeout(() => msg.remove(), 500);
        }, 5000);
    });

    // 3. Escape key to close modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeDeleteModal();
        }
    });
});
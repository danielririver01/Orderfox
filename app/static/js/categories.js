// UI Optimista para Toggle
async function toggleCategory(id, newState) {
    try {
        const response = await fetch(`/categories/${id}/toggle`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_active: newState })
        });
        
        if (!response.ok) throw new Error('Error al actualizar');
        
    } catch (error) {
        // Rollback: revertir el toggle
        const checkbox = document.querySelector(`[data-category-id="${id}"] input[type="checkbox"]`);
        if (checkbox) checkbox.checked = !newState;
        showToast('Error de conexión. Intenta de nuevo.');
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
    const categoryCards = document.querySelectorAll('.category-card');
    const noResults = document.getElementById('no-results');
    const messages = document.querySelectorAll('.flash-message');

    // 1. Live Search
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase().trim();
            
            if (clearBtn) {
                clearBtn.classList.toggle('hidden', term === '');
            }

            let visibleCount = 0;

            categoryCards.forEach(card => {
                const name = card.dataset.name || "";
                
                if (name.includes(term)) {
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
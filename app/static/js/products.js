/**
 * Products Management - Velzia
 */

// Toggle Product Status
// Toggle Product Status
async function toggleProduct(id, newState) {
    const badge = document.getElementById(`status-badge-${id}`);
    const dot = document.getElementById(`status-dot-${id}`);
    const text = document.getElementById(`status-text-${id}`);
    
    // Guardar estado anterior por si falla
    let oldClasses, oldDotClasses, oldText;
    if (badge) {
        oldClasses = badge.className;
        oldDotClasses = dot.className;
        oldText = text.textContent;

        // Actualización inmediata (Optimista)
        if (newState) {
            badge.className = "flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border transition-all duration-300 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20";
            dot.className = "w-1 h-1 rounded-full bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.4)]";
            text.textContent = 'Activo';
        } else {
            badge.className = "flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border transition-all duration-300 bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-500/20";
            dot.className = "w-1 h-1 rounded-full bg-rose-500 opacity-20";
            text.textContent = 'Inactivo';
        }
    }

    try {
        const response = await fetch(`/products/${id}/toggle`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_active: newState })
        });
        
        if (!response.ok) throw new Error('Error al actualizar');
        
    } catch (error) {
        // Revertir UI
        if (badge) {
            badge.className = oldClasses;
            dot.className = oldDotClasses;
            text.textContent = oldText;
        }
        
        const checkbox = document.querySelector(`input[onchange*="toggleProduct(${id}"]`);
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
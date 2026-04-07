// UI Optimista para Toggle
// UI Optimista para Toggle
async function toggleCategory(id, newState) {
    const badge = document.getElementById(`status-badge-${id}`);
    const dot = document.getElementById(`status-dot-${id}`);
    const text = document.getElementById(`status-text-${id}`);
    
    // Guardar estado anterior por si falla
    const oldClasses = badge.className;
    const oldDotClasses = dot.className;
    const oldText = text.textContent;

    // Actualización inmediata (Optimista)
    if (newState) {
        badge.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all duration-300 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20";
        dot.className = "w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]";
        text.textContent = 'Activa';
    } else {
        badge.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all duration-300 bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-500/20";
        dot.className = "w-1.5 h-1.5 rounded-full bg-rose-500 opacity-20";
        text.textContent = 'Inactiva';
    }

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
        // Revertir UI
        badge.className = oldClasses;
        dot.className = oldDotClasses;
        text.textContent = oldText;
        
        const checkbox = document.querySelector(`input[onchange*="toggleCategory(${id}"]`);
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
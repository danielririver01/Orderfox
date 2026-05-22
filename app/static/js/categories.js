// UI Optimista para Toggle
async function toggleCategory(id, newState, url = null) {
    const badge = document.getElementById(`status-badge-${id}`);
    const dot = document.getElementById(`status-dot-${id}`);
    const text = document.getElementById(`status-text-${id}`);
    const toggles = document.querySelectorAll(`input[data-category-id="${id}"]`);
    const endpoint = url || `/categories/${id}/status`;
    
    let oldClasses, oldDotClasses, oldText;
    if (badge) {
        oldClasses = badge.className;
        oldDotClasses = dot.className;
        oldText = text.textContent;

        if (newState) {
            badge.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all duration-300 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20";
            dot.className = "w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]";
            text.textContent = 'Activa';
        } else {
            badge.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all duration-300 bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-500/20";
            dot.className = "w-1.5 h-1.5 rounded-full bg-rose-500 opacity-20";
            text.textContent = 'Inactiva';
        }
    }

    toggles.forEach(t => t.checked = newState);

    try {
        const response = await fetch(endpoint, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ is_active: newState })
        });
        
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Error al actualizar');
        
    } catch (error) {
        if (badge) {
            badge.className = oldClasses;
            dot.className = oldDotClasses;
            text.textContent = oldText;
        }
        
        toggles.forEach(t => t.checked = !newState);
        
        if (window.showToast) {
            window.showToast(error.message || 'Error de conexión. Intenta de nuevo.', 'error');
        }
    }
}

// Search and UI Functionality
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const categoryCards = document.querySelectorAll('.category-card');
    const noResults = document.getElementById('no-results');
    const messages = document.querySelectorAll('.flash-message');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase().trim();
            let visibleCount = 0;

            categoryCards.forEach(card => {
                const name = card.dataset.name || "";
                
                if (name.includes(term)) {
                    card.style.display = 'flex';
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

    messages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transition = 'opacity 0.5s ease';
            setTimeout(() => msg.remove(), 500);
        }, 5000);
    });
});

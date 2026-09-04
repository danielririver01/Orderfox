/**
 * Products Management - Velzia
 */

// Toggle Product Status
async function toggleProduct(id, newState, url = null) {
    const badge = document.getElementById(`status-badge-${id}`);
    const dot = document.getElementById(`status-dot-${id}`);
    const text = document.getElementById(`status-text-${id}`);
    const toggles = document.querySelectorAll(`input[data-product-id="${id}"]`);
    const endpoint = url || `/products/${id}/status`;
    
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

    // Sincronizar todos los toggles del mismo producto (ej: en búsqueda y en lista)
    toggles.forEach(t => t.checked = newState);

    try {
        const response = await fetch(endpoint, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_active: newState })
        });
        
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || 'Error al actualizar');
        }
        
    } catch (error) {
        // Revertir UI
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

    // PAGINATION LOGIC
    initializeCategoryPagination();

    // 1. Live Search
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase().trim();
            let visibleCount = 0;

            // Hide pagination and show all products when searching
            document.querySelectorAll('.category-group').forEach(group => {
                const groupProducts = group.querySelectorAll('.pagination-item');
                let groupVisibleCount = 0;

                groupProducts.forEach(card => {
                    const name = card.dataset.name?.toLowerCase() || "";
                    const description = card.dataset.description?.toLowerCase() || "";

                    if (name.includes(term) || description.includes(term)) {
                        card.style.display = 'block';
                        groupVisibleCount++;
                        visibleCount++;
                    } else {
                        card.style.display = 'none';
                    }
                });

                // Show/hide pagination based on search
                const paginationControls = group.querySelector('.pagination-controls');
                if (term === '') {
                    // Reset pagination when search is cleared
                    resetCategoryPagination(group);
                    paginationControls.style.display = 'flex';
                } else {
                    paginationControls.style.display = 'none';
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

// ===== PAGINATION FUNCTIONS =====
function initializeCategoryPagination() {
    document.querySelectorAll('.category-group').forEach(group => {
        const grid = group.querySelector('.category-products-grid');
        const itemsPerPage = parseInt(grid.dataset.itemsPerPage) || 6;
        const items = grid.querySelectorAll('.pagination-item');
        const totalPages = Math.ceil(items.length / itemsPerPage);

        // Update UI with total pages
        group.querySelector('.total-pages').textContent = totalPages;

        // Hide items beyond first page
        items.forEach((item, index) => {
            item.style.display = index < itemsPerPage ? 'block' : 'none';
        });

        // Setup pagination buttons
        const prevBtn = group.querySelector('.prev-page');
        const nextBtn = group.querySelector('.next-page');
        const currentPageSpan = group.querySelector('.current-page');

        prevBtn.addEventListener('click', () => {
            const currentPage = parseInt(currentPageSpan.textContent);
            if (currentPage > 1) {
                goToPage(group, currentPage - 1, itemsPerPage);
            }
        });

        nextBtn.addEventListener('click', () => {
            const currentPage = parseInt(currentPageSpan.textContent);
            if (currentPage < totalPages) {
                goToPage(group, currentPage + 1, itemsPerPage);
            }
        });

        // Update product count in category title
        updateProductCount(group, items.length);
    });
}

function goToPage(group, pageNum, itemsPerPage) {
    const grid = group.querySelector('.category-products-grid');
    const items = grid.querySelectorAll('.pagination-item');
    const totalPages = Math.ceil(items.length / itemsPerPage);

    if (pageNum < 1 || pageNum > totalPages) return;

    const startIndex = (pageNum - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;

    items.forEach((item, index) => {
        item.style.display = (index >= startIndex && index < endIndex) ? 'block' : 'none';
    });

    // Update UI
    const currentPageSpan = group.querySelector('.current-page');
    currentPageSpan.textContent = pageNum;

    const prevBtn = group.querySelector('.prev-page');
    const nextBtn = group.querySelector('.next-page');

    prevBtn.disabled = pageNum === 1;
    nextBtn.disabled = pageNum === totalPages;

    // Scroll to category
    group.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function resetCategoryPagination(group) {
    const grid = group.querySelector('.category-products-grid');
    const itemsPerPage = parseInt(grid.dataset.itemsPerPage) || 6;
    const items = grid.querySelectorAll('.pagination-item');

    items.forEach((item, index) => {
        item.style.display = index < itemsPerPage ? 'block' : 'none';
    });

    group.querySelector('.current-page').textContent = '1';
    group.querySelector('.prev-page').disabled = true;
    group.querySelector('.next-page').disabled = items.length <= itemsPerPage;
}

function updateProductCount(group, count) {
    const countSpan = group.querySelector('.product-count');
    if (countSpan) {
        countSpan.textContent = count;
    }
}

// 1-Click Swap for AutoPhoto
async function swapProductPhoto(productId, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const btn = document.getElementById(`swap-btn-${productId}`);
    const img = document.getElementById(`product-img-${productId}`);
    if (!btn) return;

    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳';

    try {
        const response = await fetch(`/products/${productId}/swap-photo`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            // Si no hay pool, mostrar info en vez de error
            if (data.error && data.error.includes('No hay mas opciones')) {
                if (window.showToast) {
                    window.showToast('Esta foto fue asignada automáticamente. No hay alternativas en el pool.', 'info');
                }
                btn.innerHTML = originalContent;
                btn.disabled = false;
                return;
            }
            throw new Error(data.error || data.message || 'Error al cambiar la foto');
        }

        if (img && data.image_url) {
            img.src = data.image_url;
        }

        if (data.pool_remaining === 0) {
            btn.remove();
        } else {
            btn.innerHTML = originalContent;
            btn.disabled = false;
        }

        if (window.showToast) {
            window.showToast('Foto actualizada', 'success');
        }
    } catch (error) {
        btn.disabled = false;
        btn.innerHTML = originalContent;
        if (window.showToast) {
            window.showToast(error.message || 'No se pudo cambiar la foto', 'error');
        }
    }
}
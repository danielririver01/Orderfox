/**
 * Dashboard Products - Expansión de categorías y paginación
 */

function toggleCategory(element, categoryId) {
    const container = element.querySelector('.products-container');
    const expandIcon = element.querySelector('.expand-icon');

    if (!container) return; // Safety check

    const isExpanded = !container.classList.contains('hidden');

    if (isExpanded) {
        // Contraer
        container.classList.add('hidden');
        element.classList.remove('expanded');
        expandIcon.style.transform = 'rotate(0deg)';
    } else {
        // Expandir
        container.classList.remove('hidden');
        element.classList.add('expanded');
        expandIcon.style.transform = 'rotate(180deg)';
        initializePagination(element);
        element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function initializePagination(categoryElement) {
    const productsList = categoryElement.querySelector('.products-list');
    if (!productsList) return;

    const itemsPerPage = parseInt(productsList.dataset.itemsPerPage) || 6;
    const items = productsList.querySelectorAll('.pagination-item');
    const totalPages = Math.ceil(items.length / itemsPerPage);

    // Update pagination info
    const totalPagesSpan = categoryElement.querySelector('.total-pages');
    if (totalPagesSpan) totalPagesSpan.textContent = totalPages;

    // Show first page
    showPage(categoryElement, 1, itemsPerPage);

    // Setup button listeners
    const prevBtn = categoryElement.querySelector('.prev-page');
    const nextBtn = categoryElement.querySelector('.next-page');

    if (prevBtn) {
        prevBtn.onclick = () => {
            const currentPage = parseInt(categoryElement.querySelector('.current-page').textContent);
            if (currentPage > 1) {
                showPage(categoryElement, currentPage - 1, itemsPerPage);
            }
        };
    }

    if (nextBtn) {
        nextBtn.onclick = () => {
            const currentPage = parseInt(categoryElement.querySelector('.current-page').textContent);
            if (currentPage < totalPages) {
                showPage(categoryElement, currentPage + 1, itemsPerPage);
            }
        };
    }
}

function showPage(categoryElement, pageNum, itemsPerPage) {
    const productsList = categoryElement.querySelector('.products-list');
    if (!productsList) return;

    const items = productsList.querySelectorAll('.pagination-item');
    const totalPages = Math.ceil(items.length / itemsPerPage);

    if (pageNum < 1 || pageNum > totalPages) return;

    const startIndex = (pageNum - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;

    items.forEach((item, index) => {
        item.style.display = (index >= startIndex && index < endIndex) ? 'flex' : 'none';
    });

    // Update UI
    const currentPageSpan = categoryElement.querySelector('.current-page');
    const prevBtn = categoryElement.querySelector('.prev-page');
    const nextBtn = categoryElement.querySelector('.next-page');

    if (currentPageSpan) currentPageSpan.textContent = pageNum;
    if (prevBtn) prevBtn.disabled = pageNum === 1;
    if (nextBtn) nextBtn.disabled = pageNum === totalPages;
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    // All products start hidden until expanded
});


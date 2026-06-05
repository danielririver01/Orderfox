/**
 * Categories Dashboard - Panel de formulario (Desktop/Tablet)
 * Patrón: products.html + modifiers-modal.js
 */

let editingCategoryId = null;
let formImageData = null;
let formDeleteImage = false;

function openCategoryForm(categoryId = null) {
    const grid = document.getElementById('categories-grid');
    const panelWrapper = document.getElementById('category-form-panel-wrapper');

    // Expandir grid a 2 columnas
    if (grid) {
        grid.classList.remove('md:grid-cols-1');
        grid.classList.add('md:grid-cols-[1fr_380px]');
    }
    // Mostrar panel derecho
    if (panelWrapper) {
        panelWrapper.classList.remove('hidden');
        panelWrapper.classList.add('md:block');
    }

    // Ocultar FAB de escritorio
    const addBtn = document.getElementById('desktop-add-category-btn');
    if (addBtn) {
        addBtn.classList.add('hidden');
        addBtn.classList.remove('md:flex');
    }

    // Bloquear scroll del body en desktop para que no se mueva la lista de atrás
    document.body.style.overflow = 'hidden';

    // Enfocar el panel para que las flechas del teclado funcionen
    setTimeout(() => {
        const scrollArea = document.getElementById('form-scroll-area');
        if (scrollArea) scrollArea.focus();
    }, 50);

    resetForm();

    if (categoryId) {
        editingCategoryId = categoryId;
        document.getElementById('form-subtitle').textContent = 'Editando';
        document.getElementById('form-title').textContent = 'Editar Categoría';
        document.getElementById('form-delete-btn').classList.remove('hidden');
        loadCategoryData(categoryId);
    } else {
        editingCategoryId = null;
        document.getElementById('form-subtitle').textContent = 'Nueva Categoría';
        document.getElementById('form-title').textContent = 'Crear Categoría';
        document.getElementById('form-delete-btn').classList.add('hidden');
    }

    setTimeout(() => {
        document.getElementById('form-name').focus();
    }, 100);
}

function closeCategoryForm() {
    const grid = document.getElementById('categories-grid');
    const panelWrapper = document.getElementById('category-form-panel-wrapper');

    // Ocultar panel
    if (panelWrapper) {
        panelWrapper.classList.add('hidden');
        panelWrapper.classList.remove('md:block');
    }

    // Mostrar FAB de escritorio
    const addBtn = document.getElementById('desktop-add-category-btn');
    if (addBtn) {
        addBtn.classList.remove('hidden');
        addBtn.classList.add('md:flex');
    }
    
    // Volver a 1 columna
    if (grid) {
        grid.classList.remove('md:grid-cols-[1fr_380px]');
        grid.classList.add('md:grid-cols-1');
    }

    // Restaurar scroll del body
    document.body.style.overflow = '';

    resetForm();
    editingCategoryId = null;
}

function resetForm() {
    document.getElementById('form-category-id').value = '';
    document.getElementById('form-name').value = '';
    document.getElementById('form-description').value = '';
    document.getElementById('form-is-active').checked = true;
    document.getElementById('form-name-error').classList.add('hidden');
    document.getElementById('form-name-error').textContent = '';

    formImageData = null;
    formDeleteImage = false;

    const img = document.getElementById('form-image-img');
    const placeholder = document.getElementById('form-image-placeholder');
    const preview = document.getElementById('form-image-preview');
    const removeBtn = document.getElementById('form-remove-image');

    img.classList.add('hidden');
    img.src = '';
    placeholder.classList.remove('hidden');
    preview.classList.add('border-dashed');
    removeBtn.classList.add('hidden');
    document.getElementById('form-image').value = '';

    const saveBtn = document.getElementById('form-save-btn');
    saveBtn.disabled = false;
    saveBtn.innerHTML = 'Guardar';
}

async function loadCategoryData(id) {
    const saveBtn = document.getElementById('form-save-btn');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto"></div>';

    try {
        const res = await fetch(`/api/categories/${id}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await res.json();

        if (!data.success) throw new Error(data.error);

        const cat = data.data;
        document.getElementById('form-category-id').value = cat.id;
        document.getElementById('form-name').value = cat.name;
        document.getElementById('form-description').value = cat.description || '';
        document.getElementById('form-is-active').checked = cat.is_active;

        if (cat.image_url) {
            const img = document.getElementById('form-image-img');
            const placeholder = document.getElementById('form-image-placeholder');
            const preview = document.getElementById('form-image-preview');
            const removeBtn = document.getElementById('form-remove-image');

            img.src = getFullImageUrl(cat.image_url);
            img.classList.remove('hidden');
            placeholder.classList.add('hidden');
            preview.classList.remove('border-dashed');
            removeBtn.classList.remove('hidden');
            formDeleteImage = false;
        }
    } catch (err) {
        showToast(err.message || 'Error al cargar categoría', 'error');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = 'Guardar';
    }
}

async function saveCategory(e) {
    if (e) e.preventDefault();

    const name = document.getElementById('form-name').value.trim();
    const description = document.getElementById('form-description').value.trim();
    const isActive = document.getElementById('form-is-active').checked;
    const errorEl = document.getElementById('form-name-error');
    const saveBtn = document.getElementById('form-save-btn');

    errorEl.classList.add('hidden');

    if (!name) {
        errorEl.textContent = 'El nombre es obligatorio';
        errorEl.classList.remove('hidden');
        document.getElementById('form-name').focus();
        return;
    }

    saveBtn.disabled = true;
    saveBtn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto"></div>';

    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('description', description);
        formData.append('is_active', isActive);
        formData.append('csrf_token', csrfToken);

        const imageInput = document.getElementById('form-image');
        if (imageInput.files && imageInput.files[0]) {
            formData.append('image', imageInput.files[0]);
        }
        if (formDeleteImage) {
            formData.append('delete_image', 'true');
        }

        let res;
        if (editingCategoryId) {
            res = await fetch(`/api/categories/${editingCategoryId}`, {
                method: 'PUT',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            });
        } else {
            res = await fetch('/api/categories', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            });
        }

        const data = await res.json();
        if (!data.success) throw new Error(data.error);

        if (editingCategoryId) {
            updateCategoryInList(data.data);
            showToast('Categoría actualizada', 'success');
        } else {
            addCategoryToList(data.data);
            showToast('Categoría creada', 'success');
        }

        resetForm();
        editingCategoryId = null;
        document.getElementById('form-subtitle').textContent = 'Nueva Categoría';
        document.getElementById('form-title').textContent = 'Crear Categoría';
        document.getElementById('form-delete-btn').classList.add('hidden');

        updateCategoryCount();

    } catch (err) {
        showToast(err.message || 'Error al guardar', 'error');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = 'Guardar';
    }
}

function addCategoryToList(cat) {
    const list = document.getElementById('categories-list');
    const emptyState = list.querySelector('.text-center');
    if (emptyState) emptyState.remove();

    const imageUrl = cat.image_url ? getFullImageUrl(cat.image_url) : null;
    const initial = cat.name ? cat.name[0].toUpperCase() : '?';

    const html = `
    <div class="category-card flex items-center gap-4 p-4 bg-white dark:bg-[#141414] rounded-2xl border border-gray-200 dark:border-[#262626] hover:border-[#f2460d] transition-all min-w-0 overflow-hidden"
        data-category-id="${cat.id}" data-name="${cat.name.toLowerCase()}">
        <div class="w-12 h-12 rounded-xl bg-gray-50 dark:bg-[#0a0a0a] border border-gray-100 dark:border-[#262626] overflow-hidden flex-shrink-0">
            ${imageUrl
                ? `<img src="${imageUrl}" class="w-full h-full object-cover">`
                : `<div class="w-full h-full flex items-center justify-center text-[#f2460d] font-black text-lg bg-orange-50 dark:bg-orange-500/10 uppercase">${initial}</div>`
            }
        </div>
        <div class="flex-1 min-w-0">
            <h3 class="category-name font-black text-gray-900 dark:text-white tracking-tight text-base truncate">${escapeHtml(cat.name)}</h3>
            <div class="flex mt-1">
                <span id="status-badge-${cat.id}"
                    class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all duration-300
                    ${cat.is_active
                        ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20'
                        : 'bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-500/20'}">
                    <span id="status-dot-${cat.id}"
                        class="w-1.5 h-1.5 rounded-full ${cat.is_active ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' : 'bg-rose-500 opacity-20'}"></span>
                    <span id="status-text-${cat.id}">${cat.is_active ? 'Activa' : 'Inactiva'}</span>
                </span>
            </div>
            ${cat.description ? `<p class="text-[11px] text-gray-400 dark:text-gray-500 font-medium line-clamp-1 italic mt-1">"${escapeHtml(cat.description)}"</p>` : ''}
        </div>
        <div class="flex items-center gap-1 flex-shrink-0">
            <label class="relative inline-flex items-center cursor-pointer mr-2">
                <input type="checkbox" data-category-id="${cat.id}" class="sr-only peer" ${cat.is_active ? 'checked' : ''}
                    onchange="toggleCategory(${cat.id}, this.checked, '/categories/${cat.id}/status')">
                <div class="w-11 h-6 bg-red-500/10 dark:bg-red-500/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 dark:after:border-gray-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500 peer-checked:shadow-[0_0_15px_rgba(16,185,129,0.4)] shadow-inner">
                </div>
            </label>
            <button onclick="openCategoryForm(${cat.id})"
                class="hidden md:flex w-9 h-9 items-center justify-center text-gray-400 dark:text-gray-500 hover:text-[#f2460d] dark:hover:text-[#f2460d] hover:bg-orange-50 dark:hover:bg-orange-500/10 rounded-xl transition-all active:scale-90"
                title="Editar Categoría">
                <span class="material-symbols-outlined text-[20px]">edit</span>
            </button>
            <a href="/categories/${cat.id}/edit"
                class="md:hidden w-9 h-9 flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-[#f2460d] dark:hover:text-[#f2460d] hover:bg-orange-50 dark:hover:bg-orange-500/10 rounded-xl transition-all active:scale-90"
                title="Editar Categoría">
                <span class="material-symbols-outlined text-[20px]">edit</span>
            </a>
            <form action="/categories/${cat.id}/delete" method="POST" class="hidden" id="delete-form-${cat.id}">
                <input type="hidden" name="csrf_token" value="${csrfToken}">
            </form>
            <button onclick="deleteCategory(${cat.id}, '${escapeHtml(cat.name)}', '/categories/${cat.id}/delete')"
                class="w-9 h-9 flex items-center justify-center text-gray-500 dark:text-gray-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-xl transition-all active:scale-90"
                title="Eliminar Categoría">
                <span class="material-symbols-outlined text-[20px]">delete</span>
            </button>
        </div>
    </div>`;

    list.insertAdjacentHTML('beforeend', html);
}

function updateCategoryInList(cat) {
    const card = document.querySelector(`.category-card[data-category-id="${cat.id}"]`);
    if (!card) return;

    const imageUrl = cat.image_url ? getFullImageUrl(cat.image_url) : null;
    const initial = cat.name ? cat.name[0].toUpperCase() : '?';

    card.dataset.name = cat.name.toLowerCase();

    const thumb = card.querySelector('.w-12.h-12');
    if (thumb) {
        thumb.innerHTML = imageUrl
            ? `<img src="${imageUrl}" class="w-full h-full object-cover">`
            : `<div class="w-full h-full flex items-center justify-center text-[#f2460d] font-black text-lg bg-orange-50 dark:bg-orange-500/10 uppercase">${initial}</div>`;
    }

    const nameEl = card.querySelector('.category-name');
    if (nameEl) nameEl.textContent = cat.name;

    const badge = document.getElementById(`status-badge-${cat.id}`);
    const dot = document.getElementById(`status-dot-${cat.id}`);
    const text = document.getElementById(`status-text-${cat.id}`);
    if (badge) {
        badge.className = `flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all duration-300 ${cat.is_active ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20' : 'bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-500/20'}`;
    }
    if (dot) {
        dot.className = `w-1.5 h-1.5 rounded-full ${cat.is_active ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' : 'bg-rose-500 opacity-20'}`;
    }
    if (text) text.textContent = cat.is_active ? 'Activa' : 'Inactiva';

    const toggles = card.querySelectorAll(`input[data-category-id="${cat.id}"]`);
    toggles.forEach(t => t.checked = cat.is_active);
}

function removeCategoryFromList(id) {
    const card = document.querySelector(`.category-card[data-category-id="${id}"]`);
    if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(20px)';
        card.style.transition = 'all 0.3s ease';
        setTimeout(() => {
            card.remove();
            updateCategoryCount();
            const list = document.getElementById('categories-list');
            if (list.querySelectorAll('.category-card').length === 0) {
                list.innerHTML = `
                <div class="text-center py-20 bg-white dark:bg-[#141414] rounded-3xl border border-dashed border-gray-200 dark:border-[#262626]">
                    <span class="material-symbols-outlined text-gray-300 dark:text-gray-600 text-[48px] mb-4">category</span>
                    <p class="text-gray-500 dark:text-gray-400 font-medium">No hay categorías aún</p>
                    <button onclick="openCategoryForm()" class="text-[#f2460d] font-bold text-sm mt-2 inline-block transition-colors cursor-pointer">Crea tu primera categoría</button>
                </div>`;
            }
        }, 300);
    }
}

function updateCategoryCount() {
    const count = document.querySelectorAll('.category-card').length;
    const counter = document.querySelector('header p.text-xs');
    if (counter) counter.textContent = `${count} categorías`;
}

function confirmDeleteCategory() {
    if (!editingCategoryId) return;
    const name = document.getElementById('form-name').value;
    openDeleteModal(
        null,
        `¿Eliminar "${name}"? Se eliminarán también todos los productos asociados.`,
        `Eliminar categoría`,
        () => executeDelete(editingCategoryId)
    );
}

async function deleteCategory(id, name, fallbackUrl) {
    openDeleteModal(
        null,
        `¿Eliminar "${name}"? Esta acción no se puede deshacer.`,
        `Eliminar categoría`,
        async () => {
            try {
                const res = await fetch(`/api/categories/${id}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                const data = await res.json();

                if (!data.success) {
                    showToast(data.error || 'Error al eliminar', 'error');
                    return;
                }

                removeCategoryFromList(id);
                showToast('Categoría eliminada', 'success');

                if (editingCategoryId === id) {
                    closeCategoryForm();
                }
            } catch (err) {
                window.location.href = fallbackUrl;
            }
        }
    );
}

async function executeDelete(id) {
    const saveBtn = document.getElementById('form-save-btn');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto"></div>';

    try {
        const res = await fetch(`/api/categories/${id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        const data = await res.json();

        if (!data.success) throw new Error(data.error);

        removeCategoryFromList(id);
        showToast('Categoría eliminada', 'success');
        closeCategoryForm();
    } catch (err) {
        showToast(err.message || 'Error al eliminar', 'error');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = 'Guardar';
    }
}

function previewFormImage(input) {
    const img = document.getElementById('form-image-img');
    const placeholder = document.getElementById('form-image-placeholder');
    const preview = document.getElementById('form-image-preview');
    const removeBtn = document.getElementById('form-remove-image');

    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            img.src = e.target.result;
            img.classList.remove('hidden');
            placeholder.classList.add('hidden');
            preview.classList.remove('border-dashed');
            removeBtn.classList.remove('hidden');
            formDeleteImage = false;
            formImageData = input.files[0];
        };
        reader.readAsDataURL(input.files[0]);
    }
}

function removeFormImage() {
    const img = document.getElementById('form-image-img');
    const placeholder = document.getElementById('form-image-placeholder');
    const preview = document.getElementById('form-image-preview');
    const removeBtn = document.getElementById('form-remove-image');

    img.classList.add('hidden');
    img.src = '';
    placeholder.classList.remove('hidden');
    preview.classList.add('border-dashed');
    removeBtn.classList.add('hidden');
    document.getElementById('form-image').value = '';
    formImageData = null;
    formDeleteImage = true;
}

function getFullImageUrl(imagePath) {
    if (!imagePath) return null;
    if (imagePath.startsWith('http')) return imagePath;
    return `/static/${imagePath}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const panel = document.getElementById('category-form-panel-wrapper');
        if (panel && !panel.classList.contains('hidden')) {
            closeCategoryForm();
        }
    }
});

/**
 * Modifiers Panel - Velzia
 * Desktop: inline sticky panel | Mobile: slide-in modal
 */

let currentProductId = null;
let currentProductName = null;

function isMobile() {
    return window.innerWidth < 768;
}

function getEls() {
    if (isMobile()) {
        return {
            listEl: document.getElementById('modifiers-list'),
            formEl: document.getElementById('modifier-add-form'),
            nameEl: document.getElementById('modifiers-product-name'),
            nameInput: document.getElementById('modifier-name'),
            priceInput: document.getElementById('modifier-price'),
            addBtn: document.getElementById('modifier-add-btn'),
            device: 'mobile'
        };
    }
    return {
        listEl: document.getElementById('desktop-modifiers-list'),
        formEl: document.getElementById('desktop-modifier-add-form'),
        nameEl: document.getElementById('desktop-product-name'),
        nameInput: document.getElementById('desktop-modifier-name'),
        priceInput: document.getElementById('desktop-modifier-price'),
        addBtn: document.getElementById('desktop-modifier-add-btn'),
        device: 'desktop'
    };
}

async function openModifiersModal(productId, productName) {
    currentProductId = productId;
    currentProductName = productName;

    if (isMobile()) {
        await openMobile(productId, productName);
    } else {
        await openDesktop(productId, productName);
    }
}

function closeModifiersModal() {
    if (isMobile()) {
        closeMobile();
    } else {
        closeDesktop();
    }
}

function closeDesktop() {
    const panelWrapper = document.getElementById('desktop-modifiers-panel-wrapper');
    const productsGrid = document.getElementById('products-grid');
    const productsColumn = document.getElementById('products-column');

    if (productsGrid) {
        productsGrid.classList.remove('md:grid-cols-[1fr_380px]');
        productsGrid.classList.add('md:grid-cols-1');
    }
    if (panelWrapper) {
        panelWrapper.classList.add('hidden');
        panelWrapper.classList.remove('md:block', 'md:col-span-1');
    }
    if (productsColumn) {
        productsColumn.classList.add('md:col-span-2');
        productsColumn.classList.remove('md:col-span-1');
    }

    // Restore body scroll
    document.body.style.overflow = '';

    currentProductId = null;
    currentProductName = null;
}

async function openDesktop(productId, productName) {
    const els = getEls();
    const panelWrapper = document.getElementById('desktop-modifiers-panel-wrapper');
    const productsGrid = document.getElementById('products-grid');
    const productsColumn = document.getElementById('products-column');

    if (productsGrid) {
        productsGrid.classList.remove('md:grid-cols-1');
        productsGrid.classList.add('md:grid-cols-[1fr_380px]');
    }
    if (panelWrapper) {
        panelWrapper.classList.remove('hidden');
        panelWrapper.classList.add('md:block', 'md:col-span-1');
    }
    if (productsColumn) {
        productsColumn.classList.remove('md:col-span-2');
        productsColumn.classList.add('md:col-span-1');
    }

    // Lock body scroll
    document.body.style.overflow = 'hidden';

    if (typeof hasModifiersAccess !== 'undefined' && !hasModifiersAccess) return;

    els.nameEl.textContent = productName;
    els.listEl.innerHTML = loader();
    els.formEl.classList.add('hidden');
    await loadModifiers();
}

async function openMobile(productId, productName) {
    const modal = document.getElementById('modifiers-modal');
    const panel = document.getElementById('mobile-modifiers-panel');
    const els = getEls();

    if (!modal || !panel) return;

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    panel.style.transform = 'translateX(0)';

    if (typeof hasModifiersAccess !== 'undefined' && !hasModifiersAccess) return;

    els.nameEl.textContent = productName;
    els.listEl.innerHTML = loader();
    els.formEl.classList.add('hidden');

    await loadModifiers();
}

function closeMobile() {
    const modal = document.getElementById('modifiers-modal');
    const panel = document.getElementById('mobile-modifiers-panel');

    if (!panel) return;

    panel.style.transform = 'translateX(100%)';

    setTimeout(() => {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
        currentProductId = null;
        currentProductName = null;
    }, 300);
}

function loader() {
    return `<div class="flex justify-center py-8"><div class="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin"></div></div>`;
}

async function loadModifiers() {
    const els = getEls();

    try {
        const res = await fetch(`/products/${currentProductId}/api/modifiers`);
        const data = await res.json();

        if (!data.success) throw new Error(data.error);

        const modifiers = data.data.modifiers;
        els.formEl.classList.remove('hidden');

        if (modifiers.length === 0) {
            els.listEl.innerHTML = `
                <div class="text-center py-12">
                    <span class="material-symbols-outlined text-gray-600 text-[40px] mb-3">add_circle</span>
                    <p class="text-gray-500 text-sm font-medium">Sin extras aún</p>
                    <p class="text-[10px] text-gray-600 mt-1 uppercase tracking-widest font-bold">Agrega el primero abajo</p>
                </div>`;
            return;
        }

        els.listEl.innerHTML = modifiers.map(m => `
            <div class="modifier-item flex items-center gap-3 p-3.5 bg-[#0a0a0a] rounded-xl border border-[#262626] hover:border-[#333] transition-all" data-id="${m.id}">
                <label class="relative inline-flex items-center cursor-pointer flex-shrink-0">
                    <input type="checkbox" class="sr-only peer" ${m.is_active ? 'checked' : ''} onchange="toggleModifier(${m.id}, this.checked)">
                    <div class="w-10 h-5 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-5 peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-600 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"></div>
                </label>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-bold text-white truncate">${escapeHtml(m.name)}</p>
                    <p class="text-[11px] text-orange-400 font-black mt-0.5">${m.extra_price === 0 ? 'Gratis' : '+$' + formatNumber(m.extra_price)}</p>
                </div>
                <button onclick="deleteModifier(${m.id})" class="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all flex-shrink-0">
                    <span class="material-symbols-outlined text-[18px]">delete</span>
                </button>
            </div>
        `).join('');

    } catch (err) {
        els.listEl.innerHTML = `<div class="text-center py-8"><p class="text-red-400 text-sm">${err.message}</p></div>`;
    }
}

async function toggleModifier(id, newState) {
    const item = document.querySelector(`.modifier-item[data-id="${id}"]`);
    const toggle = item.querySelector('input[type="checkbox"]');

    try {
        const res = await fetch(`/products/api/modifiers/${id}/toggle`, { method: 'PATCH' });
        const data = await res.json();

        if (!data.success) throw new Error(data.error);

        toggle.checked = data.data.is_active;
        if (window.showToast) {
            window.showToast(data.data.is_active ? 'Extra activado' : 'Extra desactivado', 'success');
        }
    } catch (err) {
        toggle.checked = !newState;
        if (window.showToast) {
            window.showToast(err.message || 'Error al actualizar', 'error');
        }
    }
}

async function addModifier() {
    if (typeof hasModifiersAccess !== 'undefined' && !hasModifiersAccess) return;

    const els = getEls();
    const name = els.nameInput.value.trim();
    const price = parseInt(els.priceInput.value) || 0;

    if (!name) {
        els.nameInput.focus();
        return;
    }

    els.addBtn.disabled = true;
    els.addBtn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>';

    try {
        const res = await fetch(`/products/${currentProductId}/api/modifiers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, extra_price: price })
        });
        const data = await res.json();

        if (!data.success) throw new Error(data.error);

        els.nameInput.value = '';
        els.priceInput.value = '';

        await loadModifiers();

        if (window.showToast) {
            window.showToast(`"${name}" agregado`, 'success');
        }
    } catch (err) {
        if (window.showToast) {
            window.showToast(err.message || 'Error al crear', 'error');
        }
    } finally {
        els.addBtn.disabled = false;
        els.addBtn.innerHTML = '<span class="material-symbols-outlined text-[18px]">add</span>';
    }
}

async function deleteModifier(id) {
    const item = document.querySelector(`.modifier-item[data-id="${id}"]`);
    const name = item.querySelector('p').textContent;

    if (!confirm(`¿Eliminar "${name}"?`)) return;

    try {
        const res = await fetch(`/products/api/modifiers/${id}`, { method: 'DELETE' });
        const data = await res.json();

        if (!data.success) throw new Error(data.error);

        item.style.opacity = '0';
        item.style.transform = 'translateX(20px)';
        item.style.transition = 'all 0.3s ease';

        setTimeout(async () => {
            await loadModifiers();
        }, 300);

        if (window.showToast) {
            window.showToast(`"${name}" eliminado`, 'success');
        }
    } catch (err) {
        if (window.showToast) {
            window.showToast(err.message || 'Error al eliminar', 'error');
        }
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('modifiers-modal');
        if (modal && !modal.classList.contains('hidden')) {
            closeModifiersModal();
        }
    }
});
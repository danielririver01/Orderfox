/**
 * ui-utils.js
 * Utilidades globales de UI para Velzia.
 */

function showToast(message, category = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl shadow-lg animate-in slide-in-from-right-full fade-in duration-300 flex items-center gap-3 min-w-[300px] z-[1000]`;

    let icon = 'info';
    if (category === 'success') icon = 'check_circle';
    else if (category === 'error') icon = 'error';
    else if (category === 'warning') icon = 'warning';

    const iconColor = category === 'success' ? 'text-green-400' : category === 'warning' ? 'text-amber-400' : category === 'error' ? 'text-red-400' : 'text-blue-400';

    toast.innerHTML = `
        <span class="material-symbols-outlined text-xl ${iconColor}">
            ${icon}
        </span>
        <div class="flex-1">
            <p class="text-sm font-medium">${message}</p>
        </div>
        <button onclick="this.parentElement.remove()" class="text-slate-500 hover:text-slate-300">
            <span class="material-symbols-outlined text-lg">close</span>
        </button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.remove('slide-in-from-right-full', 'fade-in');
        toast.classList.add('animate-out', 'fade-out', 'slide-out-to-right-full');
        // Eliminación garantizada tras la animación
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 500);
    }, 3500);
}

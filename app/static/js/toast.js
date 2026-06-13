window.showToast = function (message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'info';
    if (type === 'success') icon = 'check_circle';
    else if (type === 'error') icon = 'error';
    else if (type === 'warning') icon = 'warning';

    const iconColor = type === 'success' ? 'text-green-400'
        : type === 'warning' ? 'text-amber-400'
        : type === 'error' ? 'text-red-400'
        : 'text-blue-400';

    toast.innerHTML = `
        <span class="material-symbols-outlined text-xl ${iconColor}">${icon}</span>
        <span class="flex-1">${message}</span>
        <button onclick="this.parentElement.remove()" class="text-white/50 hover:text-white/80">
            <span class="material-symbols-outlined text-lg">close</span>
        </button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 300);
    }, 6000);
};

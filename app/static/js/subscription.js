// JavaScript para la vista de suscripción

// URL de login (expuesta por subscription.html vía window.VELZIA_LOGIN_URL)
const LOGIN_URL = window.VELZIA_LOGIN_URL || '/';

// Leer cookie por nombre
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

// Abrir modal de cancelación de cuenta
function openAccountCancelModal() {
    const modal = document.getElementById('accountCancelModal');
    if (modal) {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    } else {
        console.error('ERROR: No se encontró el elemento con id="accountCancelModal"');
    }
}

// Cerrar modal de cancelación de cuenta
function closeAccountCancelModal() {
    const modal = document.getElementById('accountCancelModal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
        const checkbox = document.getElementById('confirmAccountCancel');
        if (checkbox) {
            checkbox.checked = false;
        }
        updateCancelButton();
    }
}

// Actualizar estado del botón de cancelar
function updateCancelButton() {
    const checkbox = document.getElementById('confirmAccountCancel');
    const cancelBtn = document.getElementById('confirmAccountCancelBtn');
    if (checkbox && cancelBtn) {
        cancelBtn.disabled = !checkbox.checked;
    }
}

// Cancelar suscripción (cancellation_pending: acceso hasta vencimiento)
async function cancelAccount() {
    const checkbox = document.getElementById('confirmAccountCancel');

    if (!checkbox || !checkbox.checked) {
        if (window.showToast) {
            window.showToast('Debes confirmar que entiendes que tu suscripción se cancelará al vencer', 'error');
        }
        return;
    }

    const cancelBtn = document.getElementById('confirmAccountCancelBtn');
    const originalText = cancelBtn.textContent;

    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Cancelando...';

    try {
        const csrfToken = getCookie('csrf_token');
        const response = await fetch('/dashboard/cancel-account', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            }
        });

        if (response.redirected || response.status === 401) {
            window.location.href = '/';
            return;
        }

        let data;
        try {
            data = await response.json();
        } catch (e) {
            window.location.href = '/';
            return;
        }

        if (data.success) {
            closeAccountCancelModal();
            if (window.showToast) {
                window.showToast(data.message, 'success');
            }
            setTimeout(function() {
                window.location.reload();
            }, 1500);
        } else {
            if (window.showToast) {
                window.showToast(data.message || 'Error al cancelar. Por favor, intenta de nuevo.', 'error');
            }
            cancelBtn.disabled = false;
            cancelBtn.textContent = originalText;
        }
    } catch (error) {
        console.error('Error al cancelar suscripción:', error);
        if (window.showToast) {
            window.showToast('Error al cancelar. Por favor, intenta de nuevo.', 'error');
        }
        cancelBtn.disabled = false;
        cancelBtn.textContent = originalText;
    }
}

// Reanudar suscripción (undo cancellation_pending → active)
async function resumeSubscription() {
    const btn = event.target.closest('button');
    const originalText = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span> Reactivando...';

    try {
        const csrfToken = getCookie('csrf_token');
        const response = await fetch('/dashboard/resume-subscription', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            }
        });

        let data;
        try {
            data = await response.json();
        } catch (e) {
            window.location.reload();
            return;
        }

        if (data.success) {
            if (window.showToast) {
                window.showToast(data.message, 'success');
            }
            setTimeout(function() {
                window.location.reload();
            }, 1000);
        } else {
            if (window.showToast) {
                window.showToast(data.message || 'Error al reactivar. Intenta de nuevo.', 'error');
            }
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    } catch (error) {
        console.error('Error al reactivar suscripción:', error);
        if (window.showToast) {
            window.showToast('Error al reactivar. Intenta de nuevo.', 'error');
        }
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    const checkbox = document.getElementById('confirmAccountCancel');
    if (checkbox) {
        checkbox.addEventListener('change', updateCancelButton);
    }

    const modal = document.getElementById('accountCancelModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeAccountCancelModal();
            }
        });
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeAccountCancelModal();
        }
    });
});

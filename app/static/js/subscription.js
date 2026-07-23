// JavaScript para la vista de suscripción

// Leer cookie por nombre
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

// Abrir modal de eliminación de cuenta
function openAccountDeleteModal() {
    const modal = document.getElementById('accountDeleteModal');
    if (modal) {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    } else {
        console.error('ERROR: No se encontró el elemento con id="accountDeleteModal"');
    }
}

// Cerrar modal de eliminación de cuenta
function closeAccountDeleteModal() {
    const modal = document.getElementById('accountDeleteModal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
        const checkbox = document.getElementById('confirmAccountDelete');
        if (checkbox) {
            checkbox.checked = false;
        }
        updateDeleteButton();
    }
}

// Actualizar estado del botón de eliminar
function updateDeleteButton() {
    const checkbox = document.getElementById('confirmAccountDelete');
    const deleteBtn = document.getElementById('confirmAccountDeleteBtn');
    if (checkbox && deleteBtn) {
        deleteBtn.disabled = !checkbox.checked;
    }
}

// Eliminar cuenta
async function deleteAccount() {
    const checkbox = document.getElementById('confirmAccountDelete');

    if (!checkbox || !checkbox.checked) {
        if (window.showToast) {
            window.showToast('Debes confirmar que entiendes las consecuencias de eliminar tu cuenta', 'error');
        }
        return;
    }

    const deleteBtn = document.getElementById('confirmAccountDeleteBtn');
    const originalText = deleteBtn.textContent;

    deleteBtn.disabled = true;
    deleteBtn.textContent = 'Eliminando...';

    try {
        const csrfToken = getCookie('csrf_token');
        const response = await fetch('/dashboard/delete-account', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            }
        });

        // Si hubo un redirect a login (sesión expirada), recargar
        if (response.redirected || response.status === 401) {
            window.location.href = '/';
            return;
        }

        let data;
        try {
            data = await response.json();
        } catch (e) {
            // Respuesta no es JSON (ej: redirect HTML del servidor)
            window.location.href = '/';
            return;
        }

        if (data.success) {
            deleteBtn.textContent = 'Cuenta eliminada';
            deleteBtn.classList.remove('bg-red-600', 'hover:bg-red-700');
            deleteBtn.classList.add('bg-green-600');
            setTimeout(function() {
                window.location.href = '/';
            }, 1000);
        } else {
            if (window.showToast) {
                window.showToast(data.message || 'Error al eliminar la cuenta. Por favor, intenta de nuevo.', 'error');
            }
            deleteBtn.disabled = false;
            deleteBtn.textContent = originalText;
        }
    } catch (error) {
        console.error('Error al eliminar cuenta:', error);
        if (window.showToast) {
            window.showToast('Error al eliminar la cuenta. Por favor, intenta de nuevo.', 'error');
        }
        deleteBtn.disabled = false;
        deleteBtn.textContent = originalText;
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    const checkbox = document.getElementById('confirmAccountDelete');
    if (checkbox) {
        checkbox.addEventListener('change', updateDeleteButton);
    }

    const modal = document.getElementById('accountDeleteModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeAccountDeleteModal();
            }
        });
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeAccountDeleteModal();
        }
    });
});

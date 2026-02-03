// JavaScript para la vista de suscripción

// Abrir modal de eliminación de cuenta
function openAccountDeleteModal() {
    const modal = document.getElementById('accountDeleteModal');
    
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    } else {
        console.error('ERROR: No se encontró el elemento con id="accountDeleteModal"');
    }
}

// Cerrar modal de eliminación de cuenta
function closeAccountDeleteModal() {
    const modal = document.getElementById('accountDeleteModal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = 'auto';
        
        // Resetear checkbox
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
        alert('Debes confirmar que entiendes las consecuencias de eliminar tu cuenta');
        return;
    }
    
    const deleteBtn = document.getElementById('confirmAccountDeleteBtn');
    const originalText = deleteBtn.textContent;
    
    deleteBtn.disabled = true;
    deleteBtn.textContent = 'Eliminando...';
    
    try {
        const response = await fetch('/dashboard/delete-account', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            deleteBtn.textContent = '✓ Cuenta eliminada';
            deleteBtn.classList.remove('bg-red-600', 'hover:bg-red-700');
            deleteBtn.classList.add('bg-green-600');
            
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            alert(data.message || 'Error al eliminar la cuenta. Por favor, intenta de nuevo.');
            deleteBtn.disabled = false;
            deleteBtn.textContent = originalText;
        }
    } catch (error) {
        alert('Error al eliminar la cuenta. Por favor, intenta de nuevo.');
        deleteBtn.disabled = false;
        deleteBtn.textContent = originalText;
    }
}

// Event listener para el checkbox
document.addEventListener('DOMContentLoaded', function() {
    const modalElement = document.getElementById('accountDeleteModal');
    if (!modalElement) {
        console.warn('ADVERTENCIA: No se encontró el elemento #accountDeleteModal al cargar el DOM');
    }

    const checkbox = document.getElementById('confirmAccountDelete');
    if (checkbox) {
        checkbox.addEventListener('change', updateDeleteButton);
    }
    
    // Cerrar modal al hacer clic fuera
    const modal = document.getElementById('accountDeleteModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeAccountDeleteModal();
            }
        });
    }
    
    // Cerrar modal con tecla ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeAccountDeleteModal();
        }
    });
});

/**
 * Sistema de Modal de Eliminación Profesional para Velzia
 */

let formToSubmit = null;

/**
 * Abre el modal de eliminación y prepara el formulario para enviar
 * @param {HTMLFormElement} form - El formulario que se debe enviar al confirmar
 * @param {string} message - Mensaje personalizado (opcional)
 */
function openDeleteModal(form, message = null) {
    const modal = document.getElementById('deleteModal');
    const messageEl = document.getElementById('modal-message');
    
    if (message) {
        messageEl.textContent = message;
    } else {
        messageEl.textContent = '¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.';
    }
    
    formToSubmit = form;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden'; // Prevenir scroll
}

/**
 * Cierra el modal de eliminación
 */
function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    modal.classList.add('hidden');
    document.body.style.overflow = 'auto';
    formToSubmit = null;
}

// Configurar el botón de confirmación
document.addEventListener('DOMContentLoaded', () => {
    const confirmBtn = document.getElementById('confirmDeleteBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => {
            if (formToSubmit) {
                formToSubmit.submit();
            }
            closeDeleteModal();
        });
    }

    // Escuchar la tecla ESC para cerrar el modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeDeleteModal();
        }
    });
});

/**
 * Sistema de Modal de Eliminación Profesional para Velzia
 */

let formToSubmit = null;

/**
 * Abre el modal de eliminación y prepara el formulario para enviar
 * @param {HTMLFormElement} form - El formulario que se debe enviar
 * @param {string} message - Mensaje personalizado (opcional)
 * @param {string} title - Título personalizado (opcional, ej: Eliminar "Producto")
 */
function openDeleteModal(form, message = null, title = null) {
    const modal = document.getElementById('deleteModal');
    const titleEl = document.getElementById('modal-title');
    const messageEl = document.getElementById('modal-message');
    
    if (title) {
        titleEl.textContent = title;
    } else {
        titleEl.textContent = 'Confirmar eliminación';
    }
    
    if (message) {
        messageEl.textContent = message;
    } else {
        messageEl.textContent = '¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.';
    }
    
    formToSubmit = form;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
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

/**
 * Sistema de Modal de Eliminación Profesional para Velzia
 */

let formToSubmit = null;
let deleteCallback = null;

/**
 * Abre el modal de eliminación y prepara el formulario para enviar
 * @param {HTMLFormElement} form - El formulario que se debe enviar (opcional si se usa callback)
 * @param {string} message - Mensaje personalizado (opcional)
 * @param {string} title - Título personalizado (opcional, ej: Eliminar "Producto")
 * @param {Function} callback - Función a ejecutar al confirmar (opcional, alternativa a form)
 */
function openDeleteModal(form, message = null, title = null, callback = null) {
    const modal = document.getElementById('deleteModal');
    const titleEl = document.getElementById('modal-title');
    const messageEl = document.getElementById('modal-message');

    if (title) titleEl.textContent = title;
    else titleEl.textContent = 'Confirmar eliminación';

    if (message) messageEl.textContent = message;
    else messageEl.textContent = '¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.';

    formToSubmit = form;
    deleteCallback = callback;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.style.overflow = 'hidden';
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.style.overflow = 'auto';
    formToSubmit = null;
    deleteCallback = null;
}

// Configurar el botón de confirmación
document.addEventListener('DOMContentLoaded', () => {
    const confirmBtn = document.getElementById('confirmDeleteBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => {
            if (deleteCallback) {
                deleteCallback();
            } else if (formToSubmit) {
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

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.closeDeleteModal = closeDeleteModal;

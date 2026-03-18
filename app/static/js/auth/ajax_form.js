/**
 * Manejador genérico de formularios AJAX para evitar "Confirm Form Resubmission"
 * Intercepta el submit, envía por fetch y maneja redirecciones limpias.
 */

document.addEventListener('DOMContentLoaded', () => {
    const ajaxForms = document.querySelectorAll('form[data-ajax="true"]');

    ajaxForms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalBtnContent = submitBtn ? submitBtn.innerHTML : '';
            
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span> Procesando...';
            }

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action || window.location.href, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    const text = await response.text();
                    console.error('Server error:', text);
                    throw new Error(`Error del servidor: ${response.status}`);
                }

                const contentType = response.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    throw new Error('El servidor no devolvió un JSON válido.');
                }

                const data = await response.json();

                if (data.success) {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    } else if (data.message) {
                        showFlash(data.message, 'success');
                    }
                } else {
                    if (data.message) {
                        showFlash(data.message, 'error');
                    }
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalBtnContent;
                    }
                }
            } catch (error) {
                console.error('Error:', error);
                showFlash('Ocurrió un error inesperado. Inténtalo de nuevo.', 'error');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalBtnContent;
                }
            }
        });
    });
});

function showFlash(message, type = 'info') {
    // Busca el contenedor de flash messages o crea uno
    let container = document.querySelector('.flash-container');
    if (!container) {
        // Fallback: busca el contenedor del formulario 
        const formContainer = document.querySelector('main > div > div'); 
        container = document.createElement('div');
        container.className = 'w-full mb-4 flash-container';
        if (formContainer) {
            // Insertar después del header (normalmente el 2do hijo)
            const header = formContainer.querySelector('.text-center.mb-8');
            if (header) {
                header.insertAdjacentElement('afterend', container);            } else {
                formContainer.prepend(container);
            }
        }
    }

    // Limpiar mensajes anteriores
    container.innerHTML = '';

    const div = document.createElement('div');
    
    // Style Map para diferentes categorías
    const styles = {
        'success': {
            classes: 'bg-green-50 border-green-200 text-green-600',
            icon: 'check_circle'
        },
        'error': {
            classes: 'bg-red-50 border-red-200 text-red-600',
            icon: 'error'
        },
        'danger': {
            classes: 'bg-red-50 border-red-200 text-red-600',
            icon: 'error'
        },
        'warning': {
            classes: 'bg-orange-50 border-orange-200 text-orange-600',
            icon: 'warning'
        },
        'info': {
            classes: 'bg-blue-50 border-blue-200 text-blue-600',
            icon: 'info'
        }
    };

    const style = styles[type] || styles['info'];

    div.className = `flash-message ${style.classes} border px-4 py-3 rounded-lg text-xs font-bold flex items-center gap-2 animate-fade-in-down`;
    div.innerHTML = `
        <span class="material-symbols-outlined text-[18px]">${style.icon}</span>
        ${message}
    `;

    container.appendChild(div);

    // Auto-hide using existing logic style (or logic in auth-common.js will pick it up if re-run, 
    // but better to manually trigger remove for AJAX inserted elements)
    setTimeout(() => {
        div.style.transition = 'opacity 0.5s ease';
        div.style.opacity = '0';
        setTimeout(() => div.remove(), 500);
    }, 5000);
}

// Add simple animation style if not present
if (!document.getElementById('ajax-styles')) {
    const style = document.createElement('style');
    style.id = 'ajax-styles';
    style.textContent = `
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in-down {
            animation: fadeInDown 0.3s ease-out forwards;
        }
        .animate-spin {
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
}

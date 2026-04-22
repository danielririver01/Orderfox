document.addEventListener('DOMContentLoaded', function () {
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function (message) {
        setTimeout(function () {
            message.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
            setTimeout(function () {
                message.remove();
            }, 500);
        }, 5000);
    });

    // Global UI Validation Feedback
    const requiredInputs = document.querySelectorAll('input[required], select[required], textarea[required]');
    requiredInputs.forEach(field => {
        // 1. Auto-append red asterisk to labels
        if (field.id) {
            const label = document.querySelector(`label[for="${field.id}"]`);
            if (label && !label.innerHTML.includes('text-red-500')) {
                label.innerHTML += ' <span class="text-red-500">*</span>';
            }
        } else {
            // Find parent label if no id is used but it's wrapped
            const parentLabel = field.closest('label');
            if (parentLabel && !parentLabel.innerHTML.includes('text-red-500')) {
                // Ensure we don't duplicate it if there are multiple inputs
                parentLabel.innerHTML += ' <span class="text-red-500">*</span>';
            }
        }

        // 2. Listen to HTML5 native invalid event (when user hits submit without filling it)
        field.addEventListener('invalid', function (e) {
            // Add red border and pulse animation
            field.classList.add('border-red-500', 'dark:border-red-500', 'animate-pulse');

            // Remove after 3 seconds
            setTimeout(() => {
                field.classList.remove('border-red-500', 'dark:border-red-500', 'animate-pulse');
            }, 3000);
        });
    });
});

// CSRF Protected Fetch Wrapper
// This ensures all fetch requests automatically include the CSRF token
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

if (csrfToken) {
    const originalFetch = window.fetch;
    window.fetch = async function (resource, config = {}) {
        let url;
        if (resource instanceof Request) {
            url = resource.url;
        } else {
            url = resource.toString();
        }

        const isSameOrigin = !url.startsWith('http') || url.startsWith(window.location.origin);
        const method = (config.method || (resource instanceof Request ? resource.method : 'GET')).toUpperCase();

        if (isSameOrigin && method !== 'GET') {
            // Clonar la petición si es un objeto Request para poder modificar las cabeceras
            if (resource instanceof Request) {
                const newHeaders = new Headers(resource.headers);
                newHeaders.append('X-CSRFToken', csrfToken);
                resource = new Request(resource, { headers: newHeaders });
            } else {
                if (!config.headers) config.headers = {};
                if (config.headers instanceof Headers) {
                    config.headers.append('X-CSRFToken', csrfToken);
                } else if (Array.isArray(config.headers)) {
                    config.headers.push(['X-CSRFToken', csrfToken]);
                } else {
                    config.headers['X-CSRFToken'] = csrfToken;
                }
            }
        }

        return originalFetch(resource, config);
    };
}

// Global Toast System - Velzia Premium UI
window.showToast = function (message, type = 'default') {
    const container = document.getElementById('toast-container');
    if (!container) {
        console.warn('Toast container not found in DOM');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;

    container.appendChild(toast);

    // Trigger animation
    setTimeout(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    }, 10);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
};

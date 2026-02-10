document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            message.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
            setTimeout(function() {
                message.remove();
            }, 500);
        }, 5000);
    });
});

// CSRF Protected Fetch Wrapper
// This ensures all fetch requests automatically include the CSRF token
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

if (csrfToken) {
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        let [resource, config] = args;
        
        // Ensure config object exists
        config = config || {};
        
        // Normalize headers to be an object (fetch headers can be Headers object or array)
        if (!config.headers) {
            config.headers = {};
        }

        // Add CSRF token to non-GET requests
        if (config.method && config.method.toUpperCase() !== 'GET') {
            if (config.headers instanceof Headers) {
                config.headers.append('X-CSRFToken', csrfToken);
            } else if (Array.isArray(config.headers)) {
                config.headers.push(['X-CSRFToken', csrfToken]);
            } else {
                config.headers['X-CSRFToken'] = csrfToken;
    }
        }

        return originalFetch(resource, config);
    };
}

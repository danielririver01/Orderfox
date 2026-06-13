/**
 * api-client.js — Cliente HTTP unificado con protección CSRF
 */

// Función interna para obtener el token sin declarar variables globales conflictivas
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || null;
}

async function apiFetch(url, options = {}) {
    const csrfToken = getCsrfToken();
    const method = (options.method || 'GET').toUpperCase();
    
    // Normalizar encabezados
    const headers = { ...options.headers };
    if (!headers['Content-Type'] && !(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }
    headers['X-Requested-With'] = 'XMLHttpRequest';

    if (csrfToken && method !== 'GET') {
        headers['X-CSRFToken'] = csrfToken;
    }

    try {
        const response = await fetch(url, { ...options, headers });
        
        if (!response.ok) {
            let errorBody = {};
            try { errorBody = await response.json(); } catch { }
            throw {
                success: false,
                error_code: errorBody.error_code || 'HTTP_ERROR',
                message: errorBody.message || `Error del servidor (${response.status})`,
                status: response.status
            };
        }

        try {
            return await response.json();
        } catch {
            return { success: true };
        }
    } catch (err) {
        if (err.success === false) throw err; // Re-lanzar errores ya formateados
        throw {
            success: false,
            error_code: 'NETWORK_ERROR',
            message: 'Error de conexión. Verifica tu internet.',
            original: err
        };
    }
}

window.apiFetch = apiFetch;
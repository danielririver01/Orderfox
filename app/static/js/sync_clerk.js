async function startSync() {
    console.log("Iniciando proceso de sincronización...");
    const syncMessage = document.getElementById('sync-message');
    const syncSpinner = document.getElementById('sync-spinner');
    const errorContainer = document.getElementById('error-container');

    const syncTimeout = setTimeout(() => {
        if (syncSpinner && !syncSpinner.classList.contains('hidden')) {
            console.error("Timeout de sincronización alcanzado");
            syncMessage.innerText = 'La sincronización está tardando demasiado. Por favor, refresca la página.';
            syncMessage.classList.add('text-amber-500');
        }
    }, 15000);

    try {
        if (!window.Clerk) {
            throw new Error("El SDK de Clerk no se ha cargado correctamente.");
        }

        console.log("Cargando Clerk...");
        await window.Clerk.load();
        console.log("Clerk cargado exitosamente");

        if (window.Clerk.user) {
            const user = window.Clerk.user;
            const email = user.primaryEmailAddress ? user.primaryEmailAddress.emailAddress : null;
            const clerk_id = user.id;
            const session_id = window.Clerk.session ? window.Clerk.session.id : null;

            console.log("Identidad Clerk detectada:", email);

            if (!email || !session_id) {
                throw new Error("No se pudo obtener la información de sesión de Clerk.");
            }

            console.log("Solicitando token de sesión...");
            const token = await window.Clerk.session.getToken();
            console.log("Token obtenido, enviando a backend...");

            const response = await fetch('/api/sync-clerk', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ clerk_id, email, session_id })
            });

            console.log("Respuesta del backend recibida:", response.status);
            clearTimeout(syncTimeout);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || `Error del servidor (${response.status})`);
            }

            const result = await response.json();
            if (result.success && result.redirect_url) {
                console.log("Sincronización exitosa, redirigiendo a:", result.redirect_url);

                if (result.is_new_user) {
                    syncMessage.innerText = result.message || '¡Bienvenido! Tu plan de Prueba Premium (90 días) está activado.';
                    syncMessage.classList.add('text-green-500');

                    setTimeout(() => {
                        window.location.href = result.redirect_url;
                    }, 1500);
                } else {
                    window.location.href = result.redirect_url;
                }
            } else {
                throw new Error(result.message || 'Error desconocido en la respuesta del servidor');
            }
        } else {
            console.warn("No hay usuario de Clerk activo, redirigiendo a login");
            clearTimeout(syncTimeout);
            window.location.href = LOGIN_URL;
        }
    } catch (error) {
        clearTimeout(syncTimeout);
        console.error('CRITICAL SYNC ERROR:', error);
        syncMessage.innerText = 'Error de Sincronización: ' + error.message;
        syncMessage.classList.add('text-red-500');
        if (syncSpinner) syncSpinner.classList.add('hidden');
        if (errorContainer) errorContainer.classList.remove('hidden');
    }
}

function waitForClerkAndSync() {
    if (window.Clerk) {
        startSync();
        return;
    }
    let attempts = 0;
    const maxAttempts = 100;
    const checkInterval = setInterval(() => {
        attempts++;
        if (window.Clerk) {
            clearInterval(checkInterval);
            startSync();
        } else if (attempts >= maxAttempts) {
            clearInterval(checkInterval);
            const syncMessage = document.getElementById('sync-message');
            const syncSpinner = document.getElementById('sync-spinner');
            const errorContainer = document.getElementById('error-container');
            if (syncMessage) {
                syncMessage.innerText = 'Error: No se pudo cargar el servicio de autenticación. Por favor, recarga la página.';
                syncMessage.classList.add('text-red-500');
            }
            if (syncSpinner) syncSpinner.classList.add('hidden');
            if (errorContainer) errorContainer.classList.remove('hidden');
        }
    }, 100);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', waitForClerkAndSync);
} else {
    waitForClerkAndSync();
}

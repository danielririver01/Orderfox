/**
 * Velzia Service Worker - v1.1
 */

self.addEventListener('push', function(event) {
    console.log('[Velzia SW] Push recibido');
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            // Buscar si ya tenemos una pestaña abierta del dashboard
            for (var i = 0; i < clientList.length; i++) {
                var client = clientList[i];
                if (client.url.includes('/dashboard') || client.url.includes('/orders')) {
                    // Avisar a la pestaña que debe refrescarse
                    client.postMessage({ action: 'REFRESH_ORDERS' });
                    return client.focus();
                }
            }
            // Si no hay pestaña, abrir una nueva en pedidos
            if (clients.openWindow) {
                return clients.openWindow('/orders/');
            }
        })
    );
});

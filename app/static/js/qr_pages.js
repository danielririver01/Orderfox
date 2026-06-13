function descargarQR() {
    // Usar la ruta de descarga del backend
    // Nota: Como este es un JS estático, construiremos la URL manualmente o la pasaremos desde el HTML
    // Para simplificar, usaremos RESTAURANT_SLUG definido globalmente
    const downloadUrl = `/dashboard/menu/${RESTAURANT_SLUG}/qr/download?format=png`;
    window.location.href = downloadUrl;
    mostrarToast('Descargando código QR...');
}

function copiarURL() {
    const url = MENU_URL;
    navigator.clipboard.writeText(url).then(() => {
        mostrarToast('URL copiada al portapapeles');
    }).catch(() => {
        mostrarToast('Error al copiar la URL');
    });
}

async function compartirQR() {
    const titulo = "¡Mira mi nuevo menú digital!";
    const texto = `¡Hola! 👋 Mira mi nuevo menú digital.\n\nEscanea este código QR o visita directamente el link:\n${MENU_URL}\n\n¡Haz tu pedido fácil y rápido! 📱`;
    const qrImg = document.getElementById('qrImage');

    // 1. Intentar compartir como archivo (Web Share API - Móvil)
    if (navigator.canShare && qrImg && qrImg.src) {
        try {
            const response = await fetch(qrImg.src);
            const blob = await response.blob();
            const file = new File([blob], `qr-${RESTAURANT_SLUG}.png`, { type: 'image/png' });

            if (navigator.canShare({ files: [file] })) {
                await navigator.share({
                    files: [file],
                    title: titulo,
                    text: texto
                });
                mostrarToast('Compartiendo menú...');
                return;
            }
        } catch (error) {
            console.error('Error al preparar archivos para compartir:', error);
        }
    }

    // 2. Fallback: Solo texto (Escritorio o navegadores no compatibles)
    if (navigator.share) {
        try {
            await navigator.share({
                title: titulo,
                text: texto
            });
            mostrarToast('Abriendo opciones para compartir...');
            return;
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error al compartir texto:', error);
            } else {
                return; // El usuario canceló
            }
        }
    }

    // 3. Fallback final: WhatsApp Directo (Escritorio Legacy)
    const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(texto)}`;
    window.open(whatsappUrl, '_blank');
    showToast('Abriendo WhatsApp...', 'success');
}

function volverAtras() {
    window.location.href = "/dashboard/";
}

        // Animación de entrada del QR
        document.addEventListener('DOMContentLoaded', () => {
            const qrImage = document.getElementById('qrImage');
            qrImage.style.opacity = '0';
            qrImage.style.transform = 'scale(0.9)';
            
            // Esperar a que cargue la imagen
            qrImage.onload = () => {
                qrImage.style.transition = 'all 0.5s ease-out';
                qrImage.style.opacity = '1';
                qrImage.style.transform = 'scale(1)';
            };
            
            // Si ya está cargada (caché)
            if (qrImage.complete) {
                qrImage.style.transition = 'all 0.5s ease-out';
                qrImage.style.opacity = '1';
                qrImage.style.transform = 'scale(1)';
            }
        });

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.copiarURL = copiarURL;
window.actionHandlers.descargarQR = descargarQR;
window.actionHandlers.compartirQR = function() { compartirQR(); };
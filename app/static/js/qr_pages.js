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

function compartirQR() {
    const mensaje = `¡Mira mi nuevo menú digital!\n\nEscanea este código QR o visita:\n${MENU_URL}\n\n¡Haz tu pedido fácil y rápido! 📱`;
    const url = `https://wa.me/?text=${encodeURIComponent(mensaje)}`;
    window.open(url, '_blank');
    
    mostrarToast('Abriendo WhatsApp...');
}

function volverAtras() {
    window.location.href = "/dashboard/";
}

        function mostrarToast(mensaje, tipo = 'success') {
            const toast = document.getElementById('toast');
            const toastMessage = document.getElementById('toast-message');
            
            // Cambiar color del borde según tipo
            if (tipo === 'error') {
                toast.classList.remove('border-success');
                toast.classList.add('border-red-500');
            } else {
                toast.classList.remove('border-red-500');
                toast.classList.add('border-success');
            }
            
            toastMessage.textContent = mensaje;
            toast.classList.remove('hidden');
            
            setTimeout(() => {
                toast.classList.add('hidden');
            }, 3000);
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
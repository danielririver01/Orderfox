/**
 * interactions.js - Inteligencia y Marketing para Velzia
 */

document.addEventListener('DOMContentLoaded', () => {
    checkDeepLink();
    initBackToTopButton();
});

/**
 * Inicializa el botón "back to top"
 */
function initBackToTopButton() {
    const backToTopBtn = document.getElementById('btn-back-to-top');
    if (!backToTopBtn) return;

    // Mostrar/ocultar el botón según el scroll
    window.addEventListener('scroll', () => {
        if (window.scrollY > 300) {
            backToTopBtn.classList.add('visible');
        } else {
            backToTopBtn.classList.remove('visible');
        }
    });
}

/**
 * Scroll suave hacia arriba
 */
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

/**
 * Gestiona el giro de la tarjeta
 */
function flipCard(productId) {
    const card = document.querySelector(`.product-card[data-id="${productId}"]`);
    if (!card) return;

    card.classList.toggle('flipped');

    // Si se está girando hacia la cara trasera, cargamos el QR
    if (card.classList.contains('flipped')) {
        loadQR(productId);
    }
}

/**
 * Carga el código QR dinámicamente usando la API de QRServer
 */
function loadQR(productId) {
    const qrImg = document.getElementById(`qr-${productId}`);
    const loader = qrImg.previousElementSibling; // .qr-loading

    if (!qrImg || qrImg.dataset.loaded === "true") return;

    // Construir la URL del producto (URL actual + hash del producto)
    const productUrl = `${window.location.origin}${window.location.pathname}#product-${productId}`;
    const apiUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(productUrl)}`;

    qrImg.onload = () => {
        qrImg.style.display = 'block';
        if (loader) loader.style.display = 'none';
        qrImg.dataset.loaded = "true";
    };

    qrImg.src = apiUrl;
}

/**
 * Sistema de compartido nativo o portapapeles
 */
async function shareProduct(productId, productName, categoryName) {
    const productUrl = `${window.location.origin}${window.location.pathname}#product-${productId}`;
    const shareText = getShareMessage(productName, categoryName);
    const shareData = {
        title: `Prueba esto en ${document.title}`,
        text: shareText,
        url: productUrl
    };

    try {
        if (navigator.share) {
            await navigator.share(shareData);
        } else {
            await navigator.clipboard.writeText(productUrl);
            window.showToast('¡Enlace copiado! Puedes enviarlo por WhatsApp.', 'success');
        }
    } catch (err) {
        console.error('Error al compartir:', err);
    }
}

/**
 * Determina el tipo de producto basado en el nombre de la categoría
 */
function getProductTypeText(categoryName) {
    if (!categoryName) return 'plato';

    const nameLower = categoryName.toLowerCase();

    if (nameLower.includes('bebida')) return 'bebida';
    if (nameLower.includes('postre')) return 'postre';
    if (nameLower.includes('entrada')) return 'entrada';

    return 'plato'; // default
}

/**
 * Genera el mensaje de compartir adaptado según la categoría
 */
function getShareMessage(productName, categoryName) {
    const typeText = getProductTypeText(categoryName);
    // Usar 'deliciosa' para bebida y entrada, 'delicioso' para postre y plato
    const adjective = (typeText === 'bebida' || typeText === 'entrada') ? 'deliciosa' : 'delicioso';
    return `¡Mira este ${adjective} ${typeText}: ${productName}!`;
}

/**
 * Detecta si el usuario entró por un enlace compartido (#product-ID)
 */
function checkDeepLink() {
    const hash = window.location.hash;
    if (hash && hash.startsWith('#product-')) {
        const productId = hash.split('-')[1];
        const card = document.querySelector(`.product-card[data-id="${productId}"]`);

        if (card) {
            // Esperar un poco a que la página cargue para hacer el scroll
            setTimeout(() => {
                card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                
                // Aplicar el efecto resplandor (Highlight)
                card.classList.add('product-highlight');
                
                // Limpiar la clase después de la animación para permitir que se repita si es necesario
                setTimeout(() => {
                    card.classList.remove('product-highlight');
                }, 2500);
            }, 500);
        }
    }
}

// ===== EVENT DELEGATION HANDLERS =====
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.flipCard = function (p) { flipCard(parseInt(p.id)); };
window.actionHandlers.shareProduct = function (p) { shareProduct(parseInt(p.id), p.name, p.category); };
window.actionHandlers.updateQty = function (p) { updateQty(parseInt(p.id), parseInt(p.delta)); };

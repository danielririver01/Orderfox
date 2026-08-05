 const cart = {};

        function updateQty(productId, delta) {
            const qtySpan = document.getElementById(`qty-${productId}`);
            let currentQty = parseInt(qtySpan.textContent);
            currentQty = Math.max(0, currentQty + delta);
            qtySpan.textContent = currentQty;
            
            if (currentQty > 0) {
                cart[productId] = currentQty;
            } else {
                delete cart[productId];
            }
            
            calculateTotal();
        }

        function calculateTotal() {
            let total = 0;
            const inputs = document.querySelectorAll('.product-qty-input');
            const items = [];

            inputs.forEach(input => {
                const id = input.dataset.id;
                const price = parseInt(input.dataset.price);
                const qty = parseInt(document.getElementById(`qty-${id}`).textContent);
                
                if (qty > 0) {
                    total += price * qty;
                    items.push({
                        product_id: parseInt(id),
                        quantity: qty
                    });
                }
            });

            document.getElementById('order-total').textContent = '$' + total.toLocaleString('es-CO');
            document.getElementById('items-json').value = JSON.stringify(items);
        }

        // Función para mostrar Toast Notifications
        function showToast(message, type = 'error') {
            const container = document.getElementById('toast-container');
            if (!container) return; // Si no hay contenedor, no hacer nada (o fallback a alert)

            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            
            // Icono según el tipo
            let iconSvg = '';
            if (type === 'success') {
                iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`;
            } else {
                iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>`;
            }

            toast.innerHTML = `
                ${iconSvg}
                <span>${message}</span>
            `;

            container.appendChild(toast);

            // Remover después de 3 segundos
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(-20px)';
                toast.style.transition = 'all 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        document.getElementById('order-form').onsubmit = function(e) {
            const items = JSON.parse(document.getElementById('items-json').value || '[]');
            if (items.length === 0) {
                e.preventDefault();
                showToast('Por favor selecciona al menos un producto', 'error');
                
                // Efectivo visual: sacudir o resaltar la sección de productos
                const productSection = document.querySelector('.bg-white.rounded-lg.border.border-gray-200.shadow-sm.p-6:nth-of-type(2)');
                if (productSection) {
                    productSection.classList.add('ring-2', 'ring-red-200');
                    setTimeout(() => productSection.classList.remove('ring-2', 'ring-red-200'), 500);
                }
                return;
            }

            // Modo edición: abrir modal de pago precargado con el pago actual
            // (si existe). Confirmar sobreescribe el pago; el botón secundario
            // "Guardar sin cambiar el pago" envía sin tocar el pago.
            if (window.ORDER_EDIT_MODE === true) {
                e.preventDefault();
                const editTotal = parseInt((document.getElementById('order-total').textContent || '0').replace(/[^\d]/g, ''), 10) || 0;
                if (typeof openPaymentModal === 'function') {
                    const existing = window.ORDER_EDIT_PAYMENT || null;
                    openPaymentModal({
                        total: editTotal,
                        mode: 'edit',
                        form: document.getElementById('order-form'),
                        subtitle: window.ORDER_EDIT_SUBTITLE || 'Editar venta',
                        initialMethod: existing ? existing.method : null,
                        initialAmount: existing ? existing.amount_received : null,
                    });
                } else {
                    document.getElementById('order-form').submit();
                }
                return;
            }

            // Abrir modal de pago antes de enviar el formulario
            e.preventDefault();
            const total = parseInt((document.getElementById('order-total').textContent || '0').replace(/[^\d]/g, ''), 10) || 0;
            if (typeof openPaymentModal === 'function') {
                openPaymentModal({
                    total: total,
                    mode: 'create',
                    form: document.getElementById('order-form'),
                    subtitle: 'Nuevo pedido'
                });
            } else {
                document.getElementById('order-form').submit();
            }
        };

    document.addEventListener('DOMContentLoaded', function() {
    // Precargar cantidades desde los spans qty-* (modo edición) y total inicial.
    if (document.getElementById('order-total')) {
        calculateTotal();
    }

    const searchInput = document.getElementById('product-search');
    const products = document.querySelectorAll('.product-item');
    const noResultsMessage = document.getElementById('no-results-message');

    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase().trim();
            let hasResults = false; // Bandera para rastrear coincidencias

            products.forEach(product => {
                const productName = product.querySelector('.product-name').textContent.toLowerCase();
                
                if (productName.includes(searchTerm)) {
                    product.style.display = 'flex';
                    hasResults = true; // Si al menos uno coincide, esto es true
                } else {
                    product.style.display = 'none';
                }
            });

            // Control del mensaje de "No resultados"
            if (hasResults) {
                noResultsMessage.classList.add('hidden');
            } else {
                noResultsMessage.classList.remove('hidden');
            }
        });
    }
});
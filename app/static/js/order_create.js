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

            document.getElementById('order-total').textContent = '$' + total.toLocaleString();
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
                
                // Efecto visual: sacudir o resaltar la sección de productos
                const productSection = document.querySelector('.bg-white.rounded-lg.border.border-gray-200.shadow-sm.p-6:nth-of-type(2)');
                if (productSection) {
                    productSection.classList.add('ring-2', 'ring-red-200');
                    setTimeout(() => productSection.classList.remove('ring-2', 'ring-red-200'), 500);
                }
            }
        };

    document.addEventListener('DOMContentLoaded', function() {
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
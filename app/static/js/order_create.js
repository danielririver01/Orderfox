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

// Event delegation handlers
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.updateQty = (p) => updateQty(p.id, parseInt(p.delta));
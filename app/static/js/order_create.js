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

        document.getElementById('order-form').onsubmit = async function(e) {
            e.preventDefault();
            
            const items = JSON.parse(document.getElementById('items-json').value || '[]');
            if (items.length === 0) {
                showToast('Por favor selecciona al menos un producto', 'error');
                const productSection = document.querySelector('.bg-white.rounded-lg.border.border-gray-200.shadow-sm.p-6:nth-of-type(2)');
                if (productSection) {
                    productSection.classList.add('ring-2', 'ring-red-200');
                    setTimeout(() => productSection.classList.remove('ring-2', 'ring-red-200'), 500);
                }
                return;
            }

            const submitBtn = this.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn.innerHTML;
            
            try {
                // UI: Estado de carga
                submitBtn.disabled = true;
                submitBtn.innerHTML = `
                    <svg class="animate-spin h-5 w-5 mr-2 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Procesando...
                `;

                const formData = new FormData(this);
                const data = {
                    restaurant_id: formData.get('restaurant_id'),
                    customer_name: formData.get('customer_name'),
                    customer_phone: formData.get('customer_phone'),
                    city: formData.get('city'),
                    address: formData.get('address'),
                    notes: formData.get('notes'),
                    cart: {}
                };

                // Formatear carrito para el backend
                items.forEach(item => {
                    data.cart[item.product_id] = {
                        quantity: item.quantity,
                        extras: []
                    };
                });

                const response = await fetch('/menu/api/order', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (result.success && result.init_point) {
                    showToast('¡Pedido creado! Redirigiendo al pago...', 'success');
                    // Redirigir a Mercado Pago
                    window.location.href = result.init_point;
                } else {
                    throw new Error(result.error || 'Error al procesar el pedido');
                }

            } catch (error) {
                showToast(error.message, 'error');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
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
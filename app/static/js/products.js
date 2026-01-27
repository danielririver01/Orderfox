 async function toggleProduct(id, newState) {
            try {
                const response = await fetch(`/products/${id}/toggle`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: newState })
                });
                if (!response.ok) throw new Error('Error');
            } catch (error) {
                const checkbox = document.querySelector(`[data-product-id="${id}"] input[type="checkbox"]`);
                checkbox.checked = !newState;
                showToast('Error de conexión');
            }
        }

        function showToast(message) {
            const toast = document.getElementById('toast');
            document.getElementById('toast-message').textContent = message;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 3000);
        }

        // Auto-hide flash messages after 5 seconds
        document.addEventListener('DOMContentLoaded', () => {
            const messages = document.querySelectorAll('.flash-message');
            messages.forEach(msg => {
                setTimeout(() => {
                    msg.style.opacity = '0';
                    msg.style.transition = 'opacity 0.5s ease';
                    setTimeout(() => msg.remove(), 500);
                }, 5000);
            });
        });
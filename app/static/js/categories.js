  // UI Optimista para Toggle
        async function toggleCategory(id, newState) {
            try {
                const response = await fetch(`/categories/${id}/toggle`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ is_active: newState })
                });
                
                if (!response.ok) throw new Error('Error al actualizar');
                
            } catch (error) {
                // Rollback: revertir el toggle
                const checkbox = document.querySelector(`[data-category-id="${id}"] input[type="checkbox"]`);
                checkbox.checked = !newState;
                showToast('Error de conexión. Intenta de nuevo.');
            }
        }

        function showToast(message) {
            const toast = document.getElementById('toast');
            const toastMessage = document.getElementById('toast-message');
            toastMessage.textContent = message;
            toast.classList.remove('hidden');
            setTimeout(() => {
                toast.classList.add('hidden');
            }, 3000);
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
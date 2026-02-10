  function showToast(message, type = 'default') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `<span>${message}</span>`;
            
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(-20px)';
                toast.style.transition = 'all 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        // Lógica para el toggle de la tienda
        const storeToggle = document.getElementById('store-toggle');
        if (storeToggle) {
            storeToggle.addEventListener('change', async (e) => {
                const isOpen = e.target.checked;
                try {
                    // NOTA: Usamos ruta relativa directa porque este es un archivo estático JS
                    const response = await fetch("/dashboard/toggle-status", {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_open: isOpen })
                    });
                    
                    const data = await response.json();
                    
                    // Manejo específico para Upselling (Plan Básico)
                    if (response.status === 403 && data.error === 'upgrade_required') {
                        e.target.checked = !isOpen; // Revertir el switch visualmente
                        showToast(data.message, 'error'); // Mostrar mensaje de upselling
                        
                        // Opcional: Vibración en móvil para feedback
                        if (navigator.vibrate) navigator.vibrate(200);
                        return;
                    }

                    if (data.success) {
                        showToast(`Tienda ${isOpen ? 'Abierta' : 'Cerrada'}`, isOpen ? 'success' : 'default');
                    } else {
                        throw new Error();
                    }
                } catch (error) {
                    e.target.checked = !isOpen;
                    showToast('No se pudo conectar con el servidor', 'error');
                    console.error(error);
                }
            });
        }
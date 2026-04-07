// El sistema de Toasts ahora es global y reside en auth-common.js

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

                    if (!data.success) {
                        throw new Error();
                    }

                    // Sincronizar Badge de Menú Digital
                    const menuBadge = document.getElementById('menu-status-badge');
                    const menuDot = document.getElementById('menu-status-dot-inner');
                    const menuPing = document.getElementById('menu-status-ping');
                    const menuText = document.getElementById('menu-status-text');

                    if (menuBadge) {
                        if (isOpen) {
                            menuBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all duration-300 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20";
                            menuDot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
                            menuPing.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
                            menuText.className = "text-[10px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-400";
                            menuText.textContent = 'Activo';
                        } else {
                            menuBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all duration-300 bg-rose-50 dark:bg-rose-500/10 border-rose-100 dark:border-rose-500/20";
                            menuDot.className = "relative inline-flex rounded-full h-2 w-2 bg-rose-500";
                            menuPing.className = "absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75";
                            menuText.className = "text-[10px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-400";
                            menuText.textContent = 'Inactivo';
                        }
                    }
                } catch (error) {
                    e.target.checked = !isOpen;
                    showToast('No se pudo conectar con el servidor', 'error');
                    console.error(error);
                }
            });
        }
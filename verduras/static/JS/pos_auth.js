/**
 * pos_auth.js — Comportamiento interactivo para las pantallas de Auth del POS
 * Manejo de alertas/flash: cierre manual con botón y auto-dismiss tras 5s.
 */
document.addEventListener('DOMContentLoaded', () => {
  // Manejador de click para botones de cierre de mensajes flash
  document.querySelectorAll('.flash-close').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const flash = btn.closest('.flash');
      if (flash) {
        flash.classList.add('fade-out');
        setTimeout(() => flash.remove(), 300);
      }
    });
  });

  // Auto-dismiss de mensajes flash después de 5 segundos
  document.querySelectorAll('.flash').forEach(flash => {
    setTimeout(() => {
      if (flash && flash.parentNode) {
        flash.classList.add('fade-out');
        setTimeout(() => flash.remove(), 300);
      }
    }, 5000);
  });
});

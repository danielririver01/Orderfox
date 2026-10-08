/**
 * orders.js — Gestión de estados de pedidos con modal custom.
 * Sin dependencias. CSRF via Jinja2 renderizado inline.
 */
(function () {
  'use strict';

  /* ------------------------------------------------------------------
   * Modal de confirmación propio (Promise-based)
   * ----------------------------------------------------------------*/
  var modal     = document.getElementById('order-confirm-modal');
  var overlay   = modal ? modal.querySelector('[data-order-modal-overlay]') : null;
  var iconWrap  = document.getElementById('order-modal-icon-wrap');
  var icon      = document.getElementById('order-modal-icon');
  var title     = document.getElementById('order-modal-title');
  var message   = document.getElementById('order-modal-message');
  var cancelBtn = document.getElementById('order-modal-cancel');
  var actionBtn = document.getElementById('order-modal-action');

  var _modalResolve = null;

  function showConfirm(opts) {
    if (!modal) return Promise.resolve(true);
    return new Promise(function (resolve) {
      _modalResolve = resolve;

      title.textContent = opts.title || '';
      message.textContent = opts.message || '';

      // Icono
      var colors = opts.colors || { bg: 'bg-red-500/10', text: 'text-red-500' };
      iconWrap.className = 'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ' + colors.bg;
      icon.className = 'material-symbols-outlined text-[20px] ' + colors.text;
      icon.textContent = opts.icon || 'warning';

      // Botón acción
      actionBtn.className = 'flex-1 min-h-[44px] px-4 rounded-xl text-[11px] font-black uppercase tracking-widest text-white transition-all active:scale-95';
      actionBtn.style.backgroundColor = opts.bgColor || '#ef4444';
      actionBtn.textContent = opts.actionLabel || 'Aceptar';

      modal.classList.remove('hidden');
      modal.classList.add('flex');
    });
  }

  function closeConfirmModal(result) {
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    if (_modalResolve) {
      _modalResolve(result);
      _modalResolve = null;
    }
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () { closeConfirmModal(false); });
  }
  if (overlay) {
    overlay.addEventListener('click', function () { closeConfirmModal(false); });
  }
  if (actionBtn) {
    actionBtn.addEventListener('click', function () { closeConfirmModal(true); });
  }
  if (modal) {
    modal.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeConfirmModal(false);
    });
  }

  function getCsrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  /* ------------------------------------------------------------------
   * Config de acciones
   * ----------------------------------------------------------------*/
  var CANCEL_CONFIG = {
    title: '¿Cancelar este pedido?',
    message: 'El cliente no lo recibirá y ya no se podrá cobrar. Si te equivocaste, ' +
             'puedes devolverlo a la lista desde «Cancelados».',
    icon: 'cancel',
    colors: { bg: 'bg-red-500/10', text: 'text-red-500' },
    actionLabel: 'Sí, cancelar',
    bgColor: '#ef4444'
  };

  /* ------------------------------------------------------------------
   * Función pública changeStatus
   * ----------------------------------------------------------------*/
  window.changeStatus = async function (orderId, newStatus) {
    if (newStatus === 'cancelled') {
      var confirmed = await showConfirm(CANCEL_CONFIG);
      if (!confirmed) return;
    }

    try {
      var response = await fetch('/orders/' + orderId + '/status', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrf()
        },
        body: JSON.stringify({ status: newStatus }),
      });

      if (!response.ok) {
        var data = await response.json();
        throw new Error(data.error || 'No pudimos guardar el cambio. Inténtalo otra vez.');
      }

      location.reload();
    } catch (error) {
      showToast(error.message, 'error');
    }
  };

/* showToast — defined in toast.js */
})();

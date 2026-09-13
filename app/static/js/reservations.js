/**
 * reservations.js — Acciones del panel de Reservas (v2.0).
 *
 * Delegación de eventos sobre #reservations-list: confirmar, rechazar,
 * completar y marcar no_show.
 * Sin dependencias. CSRF via data-attr expuesto por la plantilla.
 * Confirmaciones vía modal propio (sin window.confirm/prompt).
 */
(function () {
  'use strict';

  var list = document.getElementById('reservations-list');
  if (!list) return;

  var CSRF = list.dataset.csrf || '';

  /* ------------------------------------------------------------------
   * Modal de confirmación propio
   * ----------------------------------------------------------------*/
  var modal      = document.getElementById('reservation-confirm-modal');
  var overlay    = modal ? modal.querySelector('[data-reservation-modal-overlay]') : null;
  var iconWrap   = document.getElementById('res-modal-icon-wrap');
  var icon       = document.getElementById('res-modal-icon');
  var title      = document.getElementById('res-modal-title');
  var message    = document.getElementById('res-modal-message');
  var inputWrap  = document.getElementById('res-modal-input-wrap');
  var input      = document.getElementById('res-modal-input');
  var cancelBtn  = document.getElementById('res-modal-cancel');
  var actionBtn  = document.getElementById('res-modal-action');

  var _modalResolve = null;

  function openModal(opts) {
    if (!modal) return Promise.resolve(opts.confirmValue || true);
    return new Promise(function (resolve) {
      _modalResolve = resolve;

      title.textContent = opts.title || '';
      message.textContent = opts.message || '';

      // Icono
      var colors = opts.colors || { bg: 'bg-amber-500/10', text: 'text-amber-500' };
      iconWrap.className = 'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ' + colors.bg;
      icon.className = 'material-symbols-outlined text-[20px] ' + colors.text;
      icon.textContent = opts.icon || 'info';

      // Botón acción
      actionBtn.className = 'flex-1 px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all active:scale-95';
      actionBtn.style.backgroundColor = opts.bgColor || '#f59e0b';
      actionBtn.style.borderColor = 'transparent';
      actionBtn.textContent = opts.actionLabel || 'Aceptar';

      // Input opcional
      if (opts.showInput) {
        inputWrap.classList.remove('hidden');
        input.value = '';
        input.placeholder = opts.inputPlaceholder || '';
        setTimeout(function () { input.focus(); }, 80);
      } else {
        inputWrap.classList.add('hidden');
        input.value = '';
      }

      modal.classList.remove('hidden');
      modal.classList.add('flex');
    });
  }

  function closeModal(result) {
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    if (_modalResolve) {
      _modalResolve(result);
      _modalResolve = null;
    }
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () { closeModal(null); });
  }
  if (overlay) {
    overlay.addEventListener('click', function () { closeModal(null); });
  }
  if (actionBtn) {
    actionBtn.addEventListener('click', function () {
      if (!inputWrap.classList.contains('hidden')) {
        closeModal(input.value);
      } else {
        closeModal(true);
      }
    });
    actionBtn.addEventListener('mouseenter', function () {
      actionBtn.style.filter = 'brightness(1.15)';
    });
    actionBtn.addEventListener('mouseleave', function () {
      actionBtn.style.filter = '';
    });
  }
  if (modal) {
    modal.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeModal(null);
    });
  }

  /* ------------------------------------------------------------------
   * Helpers
   * ----------------------------------------------------------------*/
  function jsonFetch(url, options) {
    options = options || {};
    options.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      options.headers || {}
    );
    return fetch(url, options).then(function (resp) {
      return resp.json().catch(function () {
        throw new Error('Respuesta inválida del servidor');
      }).then(function (data) {
        if (!resp.ok || data.success === false) {
          throw new Error(data.error || 'No se pudo completar la acción');
        }
        return data;
      });
    });
  }

  function findCard(id) {
    return list.querySelector('[data-reservation-id="' + id + '"]');
  }

  function setError(card, message) {
    var existing = card.querySelector('[data-error]');
    if (existing) existing.remove();
    var el = document.createElement('p');
    el.setAttribute('data-error', '');
    el.className = 'text-xs text-red-600 dark:text-red-400 font-bold mt-2';
    el.textContent = message;
    card.appendChild(el);
  }

  function setLoading(btn, loading) {
    if (loading) {
      btn.dataset.originalText = btn.innerHTML;
      btn.disabled = true;
      btn.style.opacity = '0.6';
      btn.innerHTML = '...';
    } else {
      btn.disabled = false;
      btn.style.opacity = '';
      if (btn.dataset.originalText) btn.innerHTML = btn.dataset.originalText;
    }
  }

  function updateCardStatus(card, label, badgeClass) {
    var badge = card.querySelector('[data-status-badge]');
    if (badge) {
      badge.textContent = label;
      badge.className = 'px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border ' + badgeClass;
    }
    var actions = card.querySelector('[data-actions]');
    if (actions) actions.innerHTML = '';
  }

  /* ------------------------------------------------------------------
   * Config de acciones
   * ----------------------------------------------------------------*/
  var ACTIONS = {
    confirm: {
      method: 'PATCH',
      label: 'Confirmada',
      badge: 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20'
    },
    complete: {
      method: 'PATCH',
      label: 'Completada',
      badge: 'bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-100 dark:border-sky-500/20'
    },
    'no-show': {
      method: 'PATCH',
      label: 'No llegó',
      badge: 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-100 dark:border-red-500/20'
    },
    reject: {
      method: 'PATCH',
      label: 'Rechazada',
      badge: 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-100 dark:border-red-500/20'
    }
  };

  var MODAL_CONFIG = {
    'no-show': {
      title: 'Marcar como "No llegó"',
      message: '¿Confirmas que el cliente no se presentó a su reserva?',
      icon: 'person_off',
      colors: { bg: 'bg-amber-500/10', text: 'text-amber-500' },
      actionLabel: 'Marcar no llegó',
      bgColor: '#f59e0b'
    },
    complete: {
      title: 'Marcar como completada',
      message: '¿Confirmas que la reserva se completó con éxito?',
      icon: 'done_all',
      colors: { bg: 'bg-sky-500/10', text: 'text-sky-500' },
      actionLabel: 'Completar',
      bgColor: '#0ea5e9'
    },
    reject: {
      title: 'Rechazar reserva',
      message: '¿Seguro que deseas rechazar esta reserva?',
      icon: 'close',
      colors: { bg: 'bg-red-500/10', text: 'text-red-500' },
      actionLabel: 'Rechazar',
      bgColor: '#ef4444',
      showInput: true,
      inputPlaceholder: 'Motivo del rechazo (opcional)'
    }
  };

  /* ------------------------------------------------------------------
   * Ejecutar acción
   * ----------------------------------------------------------------*/
  function performAction(btn, action, id, body) {
    setLoading(btn, true);
    jsonFetch('/api/reservations/' + id + '/' + action, {
      method: ACTIONS[action].method,
      body: body ? JSON.stringify(body) : undefined
    })
      .then(function () {
        var card = findCard(id);
        if (!card) { window.location.reload(); return; }
        updateCardStatus(card, ACTIONS[action].label, ACTIONS[action].badge);
      })
      .catch(function (err) {
        setLoading(btn, false);
        var card = findCard(id);
        if (card) setError(card, err.message);
      });
  }

  /* ------------------------------------------------------------------
   * Delegación de eventos
   * ----------------------------------------------------------------*/
  list.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-action]');
    if (!btn || btn.disabled) return;
    var action = btn.dataset.action;
    var id = btn.dataset.id;
    if (!ACTIONS[action]) return;

    if (action === 'confirm') {
      performAction(btn, action, id, {});
      return;
    }

    var cfg = MODAL_CONFIG[action];
    if (!cfg) return;

    openModal(cfg).then(function (result) {
      if (result === null) return;
      if (action === 'reject') {
        var motivo = typeof result === 'string' ? result.trim() : '';
        performAction(btn, action, id, motivo ? { motivo: motivo } : {});
      } else {
        performAction(btn, action, id, {});
      }
    });
  });
})();

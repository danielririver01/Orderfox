/**
 * reservations.js — Acciones del panel de Reservas (v1.5).
 *
 * Delegación de eventos sobre #reservations-list: confirmar, rechazar
 * (con motivo opcional vía prompt), completar y marcar no_show.
 * Sin dependencias. CSRF via data-attr expuesto por la plantilla.
 */
(function () {
  'use strict';

  var list = document.getElementById('reservations-list');
  if (!list) return;

  var CSRF = list.dataset.csrf || '';

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

  list.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-action]');
    if (!btn || btn.disabled) return;
    var action = btn.dataset.action;
    var id = btn.dataset.id;
    if (!ACTIONS[action]) return;

    if (action === 'reject') {
      var motivo = window.prompt(
        'Motivo del rechazo (opcional — se guarda en el registro):', ''
      );
      if (motivo === null) return; // cancelado
      performAction(btn, action, id, motivo ? { motivo: motivo } : {});
      return;
    }
    if (action === 'confirm') {
      // Optimista pero reversible: el botón entra en loading hasta respuesta.
      performAction(btn, action, id, {});
      return;
    }
    if (action === 'complete' || action === 'no-show') {
      if (!window.confirm('¿Marcar esta reserva como "' + ACTIONS[action].label + '"?')) return;
      performAction(btn, action, id, {});
    }
  });
})();

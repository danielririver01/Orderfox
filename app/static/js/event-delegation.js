/**
 * event-delegation.js — Event delegation centralizado
 *
 * Reemplaza onclick= inline con data-action attributes.
 * Patrón: <button data-action="foo" data-id="123">
 *
 * Cada módulo registra sus handlers en window.actionHandlers:
 *   window.actionHandlers.foo = (params, el, event) => { ... };
 *
 * Soporta:
 * - data-action="handlerName"
 * - data-id, data-name, data-price, etc. (cualquier data-*)
 * - event.preventDefault() automático si data-action-prevent="true"
 * - event.stopPropagation() automático si data-action-stop="true"
 */

(function() {
    'use strict';

    document.addEventListener('click', function(e) {
        // Buscar el elemento más cercano con data-action
        const el = e.target.closest('[data-action]');
        if (!el) return;

        const actionName = el.dataset.action;
        if (!actionName) return;

        // Prevenir comportamiento por defecto si se indica
        if (el.dataset.actionPrevent === 'true') {
            e.preventDefault();
        }

        // Detener propagación si se indica
        if (el.dataset.actionStop === 'true') {
            e.stopPropagation();
        }

        // Recopilar todos los data-* como parámetros
        const params = {};
        for (const [key, value] of Object.entries(el.dataset)) {
            if (key !== 'action' && key !== 'actionPrevent' && key !== 'actionStop') {
                params[key] = value;
            }
        }

        // Buscar handler registrado
        if (window.actionHandlers && window.actionHandlers[actionName]) {
            try {
                window.actionHandlers[actionName](params, el, e);
            } catch (err) {
                console.error(`[event-delegation] Error en handler "${actionName}":`, err);
            }
        } else {
            console.warn(`[event-delegation] Handler no registrado: "${actionName}"`);
        }
    });

    // Registry global de handlers
    window.actionHandlers = window.actionHandlers || {};

})();

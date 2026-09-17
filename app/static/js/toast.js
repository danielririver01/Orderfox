/**
 * toast.js — Sistema unificado de notificaciones toast para Velzia.
 * Firma: showToast(message, type = 'info')
 * Tipos: info, success, error, warning, default (= info)
 */
(function () {
    'use strict';

    var ICONS = {
        info: 'info',
        success: 'check_circle',
        error: 'error',
        warning: 'warning'
    };

    function getType(type) {
        if (type === 'default' || !type) return 'info';
        if (ICONS[type]) return type;
        return 'info';
    }

    window.showToast = function (message, type) {
        var t = getType(type);
        var container = document.getElementById('toast-container');
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = 'vz-toast vz-toast--' + t;

        var icon = document.createElement('span');
        icon.className = 'material-symbols-outlined vz-toast__icon';
        icon.textContent = ICONS[t];

        var text = document.createElement('p');
        text.className = 'vz-toast__text';
        text.textContent = String(message);

        var close = document.createElement('button');
        close.className = 'vz-toast__close';
        close.setAttribute('aria-label', 'Cerrar');
        close.innerHTML = '<span class="material-symbols-outlined">close</span>';
        close.addEventListener('click', function () {
            dismiss(toast);
        });

        toast.appendChild(icon);
        toast.appendChild(text);
        toast.appendChild(close);
        container.appendChild(toast);

        requestAnimationFrame(function () {
            toast.classList.add('vz-toast--visible');
        });

        setTimeout(function () {
            dismiss(toast);
        }, 3500);
    };

    function dismiss(toast) {
        if (!toast || !toast.parentElement) return;
        toast.classList.remove('vz-toast--visible');
        toast.classList.add('vz-toast--hiding');
        setTimeout(function () {
            if (toast.parentElement) toast.remove();
        }, 300);
    }
})();

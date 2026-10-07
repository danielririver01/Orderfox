/**
 * help-tips.js — Ayudas "[?]" para campos y pantallas de Velzia.
 *
 * Regla de diseño: la ayuda se abre al TOCAR o hacer clic, nunca solo con hover.
 * En tablet y celular (donde vive el POS) el hover no existe: si la explicación
 * solo aparece al pasar el mouse, para el usuario no existe.
 *
 * Uso en plantillas:
 *   {% from 'components/field_help.html' import help %}
 *   {{ help('Cuánto le cobras al cliente. Escribe solo números: 12000') }}
 *
 * El texto de la burbuja es lo que va en data-help. La burbuja se inserta
 * debajo del campo: en el primer ancestro con [data-help-slot] si lo hay,
 * o después del contenedor del campo.
 */
(function () {
    'use strict';

    var SEL = '[data-help]';

    function closeAll(keep) {
        document.querySelectorAll('.vz-help-bubble').forEach(function (bubble) {
            if (bubble !== keep) bubble.remove();
        });
        document.querySelectorAll(SEL).forEach(function (btn) {
            btn.setAttribute('aria-expanded', 'false');
        });
    }

    function hostFor(btn) {
        return (
            btn.closest('[data-help-slot]') ||
            btn.closest('.vz-field') ||
            btn.parentElement.parentElement ||
            btn.parentElement ||
            document.body
        );
    }

    function openFor(btn) {
        var host = hostFor(btn);
        var bubble = document.createElement('div');
        bubble.className = 'vz-help-bubble';
        bubble.setAttribute('role', 'note');

        var icon = document.createElement('span');
        icon.className = 'material-symbols-outlined';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = 'lightbulb';

        var text = document.createElement('span');
        text.textContent = btn.getAttribute('data-help') || '';

        bubble.appendChild(icon);
        bubble.appendChild(text);
        host.appendChild(bubble);
        return bubble;
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest(SEL);
        if (!btn) {
            // Clic fuera: si no es dentro de una burbuja, cerramos todo.
            if (!e.target.closest('.vz-help-bubble')) closeAll(null);
            return;
        }
        e.preventDefault();
        var wasOpen = btn.getAttribute('aria-expanded') === 'true';
        closeAll(null);
        if (!wasOpen) {
            btn.setAttribute('aria-expanded', 'true');
            openFor(btn);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAll(null);
    });
})();

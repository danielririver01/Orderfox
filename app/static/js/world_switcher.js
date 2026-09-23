(function () {
    'use strict';

    var root = document.querySelector('[data-switcher-root]');
    var btn = document.getElementById('world-switcher-btn');
    var menu = document.getElementById('world-switcher-menu');
    var chevron = document.querySelector('[data-switcher-chevron]');

    function setOpen(open) {
        if (!menu || !btn) return;
        menu.classList.toggle('hidden', !open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (chevron) {
            chevron.style.transform = open ? 'rotate(180deg)' : '';
        }
    }

    function isOpen() {
        return menu && !menu.classList.contains('hidden');
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!root) return;

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            setOpen(!isOpen());
        });

        document.addEventListener('click', function (e) {
            if (isOpen() && !root.contains(e.target)) {
                setOpen(false);
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isOpen()) {
                setOpen(false);
                btn.focus();
            }
        });
    });
})();

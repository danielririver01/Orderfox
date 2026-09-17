(function () {
    'use strict';

    var SIDEBAR_KEY = 'velzia_sidebar';
    var NAV_GROUPS_KEY = 'velzia_desktop_nav_groups';
    var aside = document.getElementById('desktop-sidebar');
    var content = document.getElementById('main-content');
    var toggleBtn = document.getElementById('sidebar-toggle');
    var dropdown = document.getElementById('sidebar-dropdown');
    var avatarBtn = document.getElementById('sidebar-avatar-btn');
    var EXPANDED_CLASS = 'sidebar-expanded';

    function getState() {
        try { return localStorage.getItem(SIDEBAR_KEY) || 'collapsed'; }
        catch (e) { return 'collapsed'; }
    }

    function isExpanded() { return getState() === 'expanded'; }

    function applyState() {
        if (!aside || !content) return;
        if (isExpanded()) {
            aside.classList.add(EXPANDED_CLASS);
            content.classList.remove('lg:ml-14');
            content.classList.add('lg:ml-56');
        } else {
            aside.classList.remove(EXPANDED_CLASS);
            content.classList.remove('lg:ml-56');
            content.classList.add('lg:ml-14');
            collapseAllItems();
        }
        closeDropdown();
    }

    function collapseAllItems() {
        var items = document.querySelectorAll('#desktop-nav .nav-group-items');
        items.forEach(function (el) { el.style.maxHeight = '9999px'; });
    }

    function toggleSidebar() {
        var newState = isExpanded() ? 'collapsed' : 'expanded';
        try { localStorage.setItem(SIDEBAR_KEY, newState); } catch (e) { /* ignore */ }
        applyState();
        if (isExpanded()) initAccordion();
    }

    /* ── Accordion ── */
    function initAccordion() {
        var state;
        try { state = JSON.parse(localStorage.getItem(NAV_GROUPS_KEY) || '{}'); }
        catch (e) { state = {}; }
        var groups = document.querySelectorAll('#desktop-nav .nav-group');
        groups.forEach(function (group) {
            var name = group.getAttribute('data-group');
            var items = group.querySelector('.nav-group-items');
            var chevron = group.querySelector('.nav-chevron');
            var hasActive = items.querySelector('.bg-orange-500\\/10') !== null;
            var shouldOpen;
            if (state.hasOwnProperty(name)) shouldOpen = state[name];
            else if (name === 'operacion') shouldOpen = true;
            else shouldOpen = hasActive;
            if (shouldOpen) {
                items.style.maxHeight = items.scrollHeight + 'px';
                if (chevron) chevron.style.transform = 'rotate(180deg)';
            } else {
                items.style.maxHeight = '0px';
            }
        });
    }

    window.toggleNavGroup = function (name) {
        if (!isExpanded()) return;
        var group = document.querySelector('#desktop-nav .nav-group[data-group="' + name + '"]');
        if (!group) return;
        var items = group.querySelector('.nav-group-items');
        var chevron = group.querySelector('.nav-chevron');
        var isOpen = items.style.maxHeight && items.style.maxHeight !== '0px';
        if (isOpen) {
            items.style.maxHeight = '0px';
            if (chevron) chevron.style.transform = '';
        } else {
            items.style.maxHeight = items.scrollHeight + 'px';
            if (chevron) chevron.style.transform = 'rotate(180deg)';
        }
        var state;
        try { state = JSON.parse(localStorage.getItem(NAV_GROUPS_KEY) || '{}'); }
        catch (e) { state = {}; }
        state[name] = !isOpen;
        localStorage.setItem(NAV_GROUPS_KEY, JSON.stringify(state));
    };

    /* ── Avatar Dropdown ── */
    function toggleDropdown(e) {
        e.stopPropagation();
        if (!dropdown) return;
        var isOpen = !dropdown.classList.contains('hidden');
        if (isOpen) {
            closeDropdown();
        } else {
            dropdown.classList.remove('hidden');
            dropdown.style.opacity = '0';
            dropdown.style.transform = 'scale(0.95)';
            requestAnimationFrame(function () {
                dropdown.style.transition = 'opacity 150ms, transform 150ms';
                dropdown.style.opacity = '1';
                dropdown.style.transform = 'scale(1)';
            });
        }
    }

    function closeDropdown() {
        if (!dropdown) return;
        dropdown.style.opacity = '0';
        dropdown.style.transform = 'scale(0.95)';
        setTimeout(function () { dropdown.classList.add('hidden'); }, 150);
    }

    /* ── Init ── */
    document.addEventListener('DOMContentLoaded', function () {
        applyState();
        if (isExpanded()) initAccordion();

        if (toggleBtn) toggleBtn.addEventListener('click', toggleSidebar);
        if (avatarBtn) avatarBtn.addEventListener('click', toggleDropdown);

        document.addEventListener('click', function (e) {
            if (dropdown && !dropdown.classList.contains('hidden') &&
                !dropdown.contains(e.target) && !avatarBtn.contains(e.target)) {
                closeDropdown();
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeDropdown();
        });
    });
})();

/**
 * navigation.js — Mobile nav panel + accordion.
 * Inyectado desde navigation.html. Sin dependencias.
 */
(function () {
  'use strict';

  var panel = document.getElementById('mobile-nav-panel');
  var overlay = document.getElementById('mobile-nav-overlay');
  var toggle = document.getElementById('mobile-nav-toggle');
  var bottomNav = document.getElementById('mobile-bottom-nav');

  window.openMobileNav = function () {
    if (!panel) return;
    panel.style.transform = 'translateX(0)';
    overlay.classList.remove('hidden');
    requestAnimationFrame(function () { overlay.style.opacity = '1'; });
    if (toggle) toggle.style.display = 'none';
    if (bottomNav) bottomNav.style.display = 'none';
    document.querySelectorAll('.crc-fab, #crc-fab, [id*="fab"]').forEach(function (el) { el.style.display = 'none'; });
    document.body.style.overflow = 'hidden';
  };

  window.closeMobileNav = function () {
    if (!panel) return;
    panel.style.transform = 'translateX(-100%)';
    overlay.style.opacity = '0';
    setTimeout(function () { overlay.classList.add('hidden'); }, 300);
    if (toggle) toggle.style.display = '';
    if (bottomNav) bottomNav.style.display = '';
    document.querySelectorAll('.crc-fab, #crc-fab, [id*="fab"]').forEach(function (el) { el.style.display = ''; });
    document.body.style.overflow = '';
  };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeMobileNav();
  });

  /* El botón de menú (☰) flota arriba a la derecha: al bajar se aparta para no
     tapar lo que lees, y al subir vuelve. Con el menú abierto no se mueve. */
  if (toggle) {
    var ultimoScroll = window.scrollY;
    var apartar = function (oculto) {
      toggle.classList.toggle('opacity-0', oculto);
      toggle.classList.toggle('-translate-y-20', oculto);
      toggle.classList.toggle('pointer-events-none', oculto);
    };
    window.addEventListener('scroll', function () {
      var y = window.scrollY;
      if (panel && panel.style.transform === 'translateX(0px)') return;
      apartar(y > ultimoScroll && y > 120);
      ultimoScroll = y;
    }, { passive: true });
  }

  /* Accordion init */
  var state;
  try { state = JSON.parse(localStorage.getItem('velzia_nav_groups') || '{}'); } catch (e) { state = {}; }

  var groups = document.querySelectorAll('#mobile-nav .nav-group');
  groups.forEach(function (group) {
    var name = group.getAttribute('data-group');
    var items = group.querySelector('.nav-group-items');
    var chevron = group.querySelector('.nav-chevron');
    var hasActive = items.querySelector('.bg-orange-500\\/10') !== null;
    var shouldOpen;
    if (state.hasOwnProperty(name)) { shouldOpen = state[name]; }
    else if (name === 'operacion') { shouldOpen = true; }
    else { shouldOpen = hasActive; }
    if (shouldOpen) {
      items.style.maxHeight = items.scrollHeight + 'px';
      if (chevron) chevron.style.transform = 'rotate(180deg)';
    } else {
      items.style.maxHeight = '0px';
    }
  });
})();

function toggleMobileNavGroup(name) {
  var group = document.querySelector('#mobile-nav .nav-group[data-group="' + name + '"]');
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
  try { state = JSON.parse(localStorage.getItem('velzia_nav_groups') || '{}'); } catch (e) { state = {}; }
  state[name] = !isOpen;
  localStorage.setItem('velzia_nav_groups', JSON.stringify(state));
}

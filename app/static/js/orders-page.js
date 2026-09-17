/**
 * orders-page.js — Funciones de la página de pedidos (sort, sonido, pending).
 * Variable LAST_ORDER_ID se inyecta desde un data-attr en el DOM.
 */
(function () {
  'use strict';

  var el = document.getElementById('orders-data');
  var LAST_ORDER_ID = el ? parseInt(el.dataset.lastOrderId || '0', 10) : 0;

  window.toggleSort = function () {
    var currentSort = localStorage.getItem('orders_sort_order') || 'asc';
    var newSort = currentSort === 'asc' ? 'desc' : 'asc';
    localStorage.setItem('orders_sort_order', newSort);

    var url = new URL(window.location);
    url.searchParams.set('sort', newSort);
    window.location.href = url.href;
  };

  window.updateSortIcon = function () {
    var url = new URL(window.location);
    var sort = url.searchParams.get('sort') || localStorage.getItem('orders_sort_order') || 'asc';
    var icon = document.getElementById('sort-icon');
    var btn = document.getElementById('sort-toggle-btn');

    if (icon) {
      icon.textContent = sort === 'asc' ? 'arrow_upward' : 'arrow_downward';
    }

    if (btn && sort === 'desc') {
      btn.classList.add('bg-blue-100', 'dark:bg-blue-500/10', 'text-blue-500');
    }
  };

  window.showAllPending = function () {
    document.querySelectorAll('.pending-order-item').forEach(function (el) { el.classList.remove('hidden'); });
    var loadMore = document.getElementById('load-more-pending');
    if (loadMore) loadMore.classList.add('hidden');
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.updateSortIcon === 'function') window.updateSortIcon();

    var url = new URL(window.location);
    var savedSort = localStorage.getItem('orders_sort_order');
    if (!url.searchParams.has('sort') && savedSort) {
      url.searchParams.set('sort', savedSort);
      window.location.replace(url.href);
    }
  });
})();

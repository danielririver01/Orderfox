async function changeStatus(orderId, newStatus) {
  try {
    await apiFetch(`/orders/${orderId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus }),
    });
    location.reload();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

// Event delegation handlers
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.openOrderDetail = (p) => openOrderDetail(parseInt(p.id));
window.actionHandlers.changeOrderStatus = (p) => changeStatus(parseInt(p.id), p.status);
window.actionHandlers.showAllPending = showAllPending;
window.actionHandlers.toggleSort = toggleSort;
if (typeof toggleSound !== 'undefined') {
  window.actionHandlers.toggleSound = toggleSound;
}
if (typeof closeOrderDetail !== 'undefined') {
  window.actionHandlers.closeOrderDetail = closeOrderDetail;
}
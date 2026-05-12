async function changeStatus(orderId, newStatus) {
  try {
    const response = await fetch(`/orders/${orderId}/status`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": "{{ csrf_token() }}"
      },
      body: JSON.stringify({ status: newStatus }),
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Error al cambiar estado");
    }

    // If detail panel is open for this order, refresh it
    if (typeof refreshOrderPanel === 'function' && typeof currentOrderId !== 'undefined' && currentOrderId === orderId) {
      // Reload the page to refresh both list and panel
      location.reload();
    } else {
      location.reload();
    }
  } catch (error) {
    showToast(error.message);
  }
}
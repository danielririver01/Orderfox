async function changeStatus(orderId, newStatus) {
        try {
          const response = await fetch(`/orders/${orderId}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: newStatus }),
          });

          if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || "Error al cambiar estado");
          }

          // Recargar página para ver cambios
          location.reload();
        } catch (error) {
          showToast(error.message);
        }
      }

      function showToast(message) {
        const toast = document.getElementById("toast");
        document.getElementById("toast-message").textContent = message;
        toast.classList.remove("hidden");
        setTimeout(() => toast.classList.add("hidden"), 3000);
      }
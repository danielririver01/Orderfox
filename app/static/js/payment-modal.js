/**
 * Payment Modal / Cash Register - Velzia
 * Modal de pago reutilizable: Efectivo (calcula cambio), Nequi/Bancolombia, Tarjeta
 * o "Solo tomar pedido" (sin pago).
 *
 * Uso:
 *   openPaymentModal({ total, orderId, mode, form, subtitle })
 *   - mode='create'  : setea hidden fields del form de creación y hace form.submit()
 *   - mode='register': fetch POST /orders/<id>/payment y refresca el panel
 *   - mode='edit'    : como 'create', pero precarga el pago existente
 *                      (initialMethod / initialAmount) y permite sobreescribirlo.
 */

let paymentModalState = {
    total: 0,
    orderId: null,
    mode: 'create', // 'create' | 'register' | 'edit'
    method: null,   // 'cash' | 'nequi' | 'bancolombia' | 'card'
    transfer: 'nequi',
    form: null,     // formulario a enviar en modo 'create' / 'edit'
    requestInFlight: false,
    onSuccess: null,
};

function formatCOP(value) {
    return '$' + Number(value || 0).toLocaleString('es-CO');
}

function openPaymentModal(opts) {
    const modal = document.getElementById('payment-modal');
    if (!modal) return;

    paymentModalState.total = opts.total || 0;
    paymentModalState.orderId = opts.orderId || null;
    paymentModalState.mode = opts.mode || 'create';
    paymentModalState.form = opts.form || null;
    paymentModalState.onSuccess = opts.onSuccess || null;
    paymentModalState.method = null;
    paymentModalState.transfer = 'nequi';
    paymentModalState.requestInFlight = false;

    document.getElementById('pm-total').textContent = formatCOP(paymentModalState.total);
    document.getElementById('pm-subtitle').textContent = opts.subtitle || 'Pedido';

    hideError();
    resetMethodPanels();
    resetCash();

    // Texto del botón secundario según el modo
    const secondaryBtn = document.getElementById('pm-secondary');
    if (secondaryBtn) {
        if (paymentModalState.mode === 'edit') {
            secondaryBtn.textContent = 'Guardar sin cambiar el pago';
        } else if (paymentModalState.mode === 'register') {
            secondaryBtn.textContent = 'Cancelar';
        } else {
            secondaryBtn.textContent = 'Solo tomar pedido (sin pago)';
        }
    }

    // Precargar pago existente (modo edición)
    if (opts.initialMethod) {
        selectPaymentMethod(opts.initialMethod);
        if (opts.initialMethod === 'cash' && opts.initialAmount) {
            document.getElementById('pm-cash-amount').value = String(opts.initialAmount);
            updateCashFeedback();
        }
    }

    document.body.style.overflow = 'hidden';
    modal.classList.remove('hidden');
}

function closePaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (!modal) return;
    if (paymentModalState.requestInFlight) return;
    document.body.style.overflow = '';
    modal.classList.add('hidden');
    paymentModalState.method = null;
    paymentModalState.form = null;
    paymentModalState.onSuccess = null;
}

function hideError() {
    const err = document.getElementById('pm-error');
    if (err) {
        err.classList.add('hidden');
        err.textContent = '';
    }
}

function showError(message) {
    const err = document.getElementById('pm-error');
    if (!err) return;
    err.textContent = message;
    err.classList.remove('hidden');
}

function resetMethodPanels() {
    document.querySelectorAll('.pm-method').forEach(btn => {
        btn.classList.remove('border-[#f2460d]', 'bg-[#f2460d]/10');
        btn.classList.add('border-[#262626]', 'bg-white/5');
    });
    ['pm-cash-panel', 'pm-transfer-panel', 'pm-card-panel'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
}

function selectPaymentMethod(method) {
    if (paymentModalState.requestInFlight) return;
    paymentModalState.method = method;
    hideError();

    resetMethodPanels();
    const btn = document.querySelector(`[data-pm-method="${method}"]`);
    if (btn) {
        btn.classList.add('border-[#f2460d]', 'bg-[#f2460d]/10');
        btn.classList.remove('border-[#262626]', 'bg-white/5');
    }

    if (method === 'cash') {
        document.getElementById('pm-cash-panel').classList.remove('hidden');
        updateCashFeedback();
    } else if (method === 'nequi' || method === 'bancolombia') {
        document.getElementById('pm-transfer-panel').classList.remove('hidden');
        selectTransfer(method);
    } else if (method === 'card') {
        document.getElementById('pm-card-panel').classList.remove('hidden');
    }
}

function selectTransfer(transfer) {
    paymentModalState.transfer = transfer;
    paymentModalState.method = transfer;
    document.querySelectorAll('.pm-transfer').forEach(btn => {
        btn.classList.remove('ring-2', 'ring-[#f2460d]', 'ring-offset-2', 'ring-offset-[#141414]');
    });
    const current = document.querySelector(`.pm-transfer:nth-child(${transfer === 'nequi' ? 1 : 2})`);
    if (current) current.classList.add('ring-2', 'ring-[#f2460d]', 'ring-offset-2', 'ring-offset-[#141414]');
}

function getCashAmount() {
    const raw = document.getElementById('pm-cash-amount').value;
    const parsed = parseInt(raw.replace(/\D/g, ''), 10);
    return isNaN(parsed) ? 0 : parsed;
}

function addBill(value) {
    const input = document.getElementById('pm-cash-amount');
    input.value = (getCashAmount() + value).toString();
    updateCashFeedback();
}

function clearCash() {
    document.getElementById('pm-cash-amount').value = '';
    updateCashFeedback();
}

function resetCash() {
    document.getElementById('pm-cash-amount').value = '';
    const changeEl = document.getElementById('pm-cash-change');
    const shortEl = document.getElementById('pm-cash-short');
    if (changeEl) changeEl.classList.add('hidden');
    if (shortEl) shortEl.classList.add('hidden');
}

function updateCashFeedback() {
    const received = getCashAmount();
    const total = paymentModalState.total;
    const changeEl = document.getElementById('pm-cash-change');
    const shortEl = document.getElementById('pm-cash-short');
    const changeAmt = document.getElementById('pm-cash-change-amount');
    const shortAmt = document.getElementById('pm-cash-short-amount');

    if (received === 0) {
        if (changeEl) changeEl.classList.add('hidden');
        if (shortEl) shortEl.classList.add('hidden');
        return;
    }

    if (received >= total) {
        if (shortEl) shortEl.classList.add('hidden');
        if (changeEl) {
            changeEl.classList.remove('hidden');
            changeAmt.textContent = formatCOP(received - total);
        }
    } else {
        if (changeEl) changeEl.classList.add('hidden');
        if (shortEl) {
            shortEl.classList.remove('hidden');
            shortAmt.textContent = formatCOP(total - received);
        }
    }
}

function confirmPayment() {
    if (paymentModalState.requestInFlight) return;
    if (!paymentModalState.method) {
        showError('Selecciona un método de pago');
        return;
    }

    if (paymentModalState.mode === 'register') {
        confirmPaymentRegister();
    } else {
        // create y edit envían el formulario con los campos de pago ocultos.
        confirmPaymentCreate();
    }
}

function confirmPaymentCreate() {
    const form = paymentModalState.form;
    if (!form) return;

    let amount = null;
    if (paymentModalState.method === 'cash') {
        const received = getCashAmount();
        if (received === 0) {
            showError('Indica cuánto pagó el cliente');
            return;
        }
        if (received < paymentModalState.total) {
            showError('Falta dinero: ' + formatCOP(paymentModalState.total - received));
            return;
        }
        amount = received;
    }

    setHidden(form, 'payment_method', paymentModalState.method);
    setHidden(form, 'amount_received', amount);
    setHidden(form, 'change_due', paymentModalState.method === 'cash' ? (amount - paymentModalState.total) : null);

    document.body.style.overflow = '';
    form.submit();
}

/**
 * Botón secundario del modal:
 * - create:  enviar el form sin pago ("Solo tomar pedido")
 * - edit:    enviar el form sin tocar el pago ("Guardar sin cambiar el pago")
 * - register: cerrar el modal (no hay form)
 */
function submitWithoutPayment() {
    const form = paymentModalState.form;
    if (form) {
        document.body.style.overflow = '';
        form.submit();
    } else {
        closePaymentModal();
    }
}

function setHidden(form, name, value) {
    let input = form.querySelector(`input[name="${name}"]`);
    if (!input) {
        input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        form.appendChild(input);
    }
    input.value = value === null || value === undefined ? '' : String(value);
}

function confirmPaymentRegister() {
    const confirmBtn = document.getElementById('pm-confirm');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const payload = {
        payment_method: paymentModalState.method,
        amount_received: paymentModalState.method === 'cash' ? getCashAmount() : null,
    };

    if (paymentModalState.method === 'cash' && getCashAmount() === 0) {
        showError('Indica cuánto pagó el cliente');
        return;
    }

    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    paymentModalState.requestInFlight = true;
    confirmBtn.disabled = true;
    confirmBtn.classList.add('opacity-60');

    fetch(`/orders/${paymentModalState.orderId}/payment`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
    })
        .then(async (res) => {
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(body.error || 'Error al registrar el pago');
            }
            return body;
        })
        .then((body) => {
            closePaymentModal();
            if (typeof paymentModalState.onSuccess === 'function') {
                paymentModalState.onSuccess(body.data);
            } else if (typeof refreshOrderPanel === 'function' && paymentModalState.orderId) {
                refreshOrderPanel(paymentModalState.orderId);
            } else {
                window.location.reload();
            }
        })
        .catch((err) => {
            showError(err.message);
        })
        .finally(() => {
            paymentModalState.requestInFlight = false;
            confirmBtn.disabled = false;
            confirmBtn.classList.remove('opacity-60');
        });
}

// Formatear input de efectivo mientras se escribe (dígitos + punto separador de miles)
document.addEventListener('DOMContentLoaded', () => {
    const cashInput = document.getElementById('pm-cash-amount');
    if (cashInput) {
        cashInput.addEventListener('input', () => {
            const cleaned = cashInput.value.replace(/[^\d.]/g, '');
            if (cleaned !== cashInput.value) cashInput.value = cleaned;
            updateCashFeedback();
        });
    }
});

 const password = document.getElementById('password');
const confirm = document.getElementById('confirm_password');
const submitBtn = document.getElementById('submitBtn');

const checks = {
    upper: document.getElementById('check-upper'),
    number: document.getElementById('check-number'),
    match: document.getElementById('check-match')
};

function validate() {
    const val = password.value;
    const valConfirm = confirm.value;

    // Al menos una mayúscula (en cualquier posición)
    const hasUpper = /[A-Z]/.test(val);
    // Incluir números
    const hasNumber = /[0-9]/.test(val);
    // Longitud mínima 8
    const isLongEnough = val.length >= 8;
    // Coinciden
    const matches = val === valConfirm && val.length > 0;

    updateUI(checks.upper, hasUpper);
    updateUI(checks.number, hasNumber);
    updateUI(checks.match, matches && isLongEnough);

    submitBtn.disabled = !(hasUpper && hasNumber && matches && isLongEnough);
}

        function updateUI(el, isValid) {
            const icon = el.querySelector('.material-symbols-outlined');
            if (isValid) {
                el.classList.remove('text-gray-400');
                el.classList.add('text-green-500', 'font-medium');
                icon.innerText = 'check_circle';
            } else {
                el.classList.remove('text-green-500', 'font-medium');
                el.classList.add('text-gray-400');
                icon.innerText = 'circle';
            }
        }

        password.addEventListener('input', validate);
        confirm.addEventListener('input', validate);
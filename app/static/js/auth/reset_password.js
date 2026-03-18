 const password = document.getElementById('password');
const confirm = document.getElementById('confirm_password');
const submitBtn = document.getElementById('submitBtn');

const checks = {
    upper: document.getElementById('check-upper'),
    number: document.getElementById('check-number'),
    length: document.getElementById('check-length'),
    match: document.getElementById('check-match')
};

function validate() {
    const val = password.value;
    const valConfirm = confirm.value;

    const hasUpper = /[A-Z]/.test(val);
    const hasNumber = /[0-9]/.test(val);
    const isLongEnough = val.length >= 8;
    const matches = val === valConfirm && val.length > 0;

    updateUI(checks.upper, hasUpper);
    updateUI(checks.number, hasNumber);
    updateUI(checks.length, isLongEnough);
    updateUI(checks.match, matches);

    submitBtn.disabled = !(hasUpper && hasNumber && isLongEnough && matches);
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
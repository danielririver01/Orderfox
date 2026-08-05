tailwind.config = { darkMode: 'class' }

window.addEventListener('load', () => {
    const password = document.getElementById('password');
    const accept = document.getElementById('accept_terms');
    const sync = () => {
        if (password) { validate(); return; }
        const btn = document.getElementById('submitBtn');
        if (!btn) return;
        const ok = !accept || accept.checked;
        btn.disabled = !ok;
        btn.style.background = ok ? '#f97316' : '#27201a';
        btn.style.color = ok ? 'white' : '#4b4440';
        btn.style.boxShadow = ok ? '0 10px 28px -10px rgba(249,115,22,0.65)' : 'none';
    };
    if (accept) accept.addEventListener('change', sync);
    sync();
});

const password = document.getElementById('password');
const confirm = document.getElementById('confirm_password');
const submitBtn = document.getElementById('submitBtn');

const checks = {
    length: document.getElementById('check-length'),
    upper: document.getElementById('check-upper'),
    number: document.getElementById('check-number'),
    match: document.getElementById('check-match')
};

function validate() {
    if (!password || !confirm) return;
    const val = password.value;
    const valConfirm = confirm.value;

    const isLength = val.length >= 8;
    const isUpper = /^[A-Z]/.test(val);
    const hasNumber = /[0-9]/.test(val);
    const matches = val === valConfirm && val.length > 0;

    updateUI(checks.length, isLength);
    updateUI(checks.upper, isUpper);
    updateUI(checks.number, hasNumber);
    updateUI(checks.match, matches);

    const accept = document.getElementById('accept_terms');
    const accepted = !accept || accept.checked;
    submitBtn.disabled = !(isLength && isUpper && hasNumber && matches && accepted);
    submitBtn.style.background = submitBtn.disabled ? '#27201a' : '#f97316';
    submitBtn.style.color = submitBtn.disabled ? '#4b4440' : 'white';
    submitBtn.style.boxShadow = submitBtn.disabled ? 'none' : '0 10px 28px -10px rgba(249,115,22,0.65)';
}

function updateUI(el, isValid) {
    if (!el) return;
    const icon = el.querySelector('.material-symbols-outlined');
    if (isValid) {
        el.classList.add('valid');
        icon.innerText = 'check_circle';
    } else {
        el.classList.remove('valid');
        icon.innerText = 'circle';
    }
}

if (password) password.addEventListener('input', validate);
if (confirm) confirm.addEventListener('input', validate);

function togglePass(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (input.type === 'password') {
        input.type = 'text';
        icon.innerText = 'visibility_off';
    } else {
        input.type = 'password';
        icon.innerText = 'visibility';
    }
}

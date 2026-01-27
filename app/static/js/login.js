    const togglePassword = document.getElementById('toggle-password');
    const password = document.getElementById('password');
    togglePassword.addEventListener('click', function() {
        if (password.type === 'password') {
            password.type = 'text';
            togglePassword.innerHTML = '<span class="material-symbols-outlined text-[20px]">visibility</span>';
        } else {
            password.type = 'password';
            togglePassword.innerHTML = '<span class="material-symbols-outlined text-[20px]">visibility_off</span>';
        }
    });
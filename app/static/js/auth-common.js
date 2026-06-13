document.addEventListener('DOMContentLoaded', function () {
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function (message) {
        setTimeout(function () {
            message.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
            setTimeout(function () {
                message.remove();
            }, 500);
        }, 5000);
    });

    // Global UI Validation Feedback
    const requiredInputs = document.querySelectorAll('input[required], select[required], textarea[required]');
    requiredInputs.forEach(field => {
        // 1. Auto-append red asterisk to labels
        if (field.id) {
            const label = document.querySelector(`label[for="${field.id}"]`);
            if (label && !label.innerHTML.includes('text-red-500')) {
                label.innerHTML += ' <span class="text-red-500">*</span>';
            }
        } else {
            // Find parent label if no id is used but it's wrapped
            const parentLabel = field.closest('label');
            if (parentLabel && !parentLabel.innerHTML.includes('text-red-500')) {
                // Ensure we don't duplicate it if there are multiple inputs
                parentLabel.innerHTML += ' <span class="text-red-500">*</span>';
            }
        }

        // 2. Listen to HTML5 native invalid event (when user hits submit without filling it)
        field.addEventListener('invalid', function (e) {
            // Add red border and pulse animation
            field.classList.add('border-red-500', 'dark:border-red-500', 'animate-pulse');

            // Remove after 3 seconds
            setTimeout(() => {
                field.classList.remove('border-red-500', 'dark:border-red-500', 'animate-pulse');
            }, 3000);
        });
    });
});

// CSRF Token handling is centralized in api-client.js
// Use window.apiFetch() for CSRF-protected requests


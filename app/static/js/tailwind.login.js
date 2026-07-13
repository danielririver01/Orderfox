window.tailwind = window.tailwind || {};
window.tailwind.config = {
    darkMode: "media",
    theme: {
        extend: {
            colors: {
                "primary": "#7c3aed",
                "primary-hover": "#6d28d9",
                "background-light": "#faf8f6",
                "background-dark": "#0a0a0a",
            },
            fontFamily: {
                "sans": ["Plus Jakarta Sans", "system-ui", "sans-serif"],
                "display": ["Fraunces", "Georgia", "serif"]
            },
            borderRadius: {
                "DEFAULT": "0.25rem",
                "lg": "0.5rem",
                "xl": "0.75rem",
                "full": "9999px"
            },
        },
    },
}

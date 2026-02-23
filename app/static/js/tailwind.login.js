window.tailwind = window.tailwind || {};
window.tailwind.config = {
    darkMode: "media",
    theme: {
        extend: {
            colors: {
                "primary": "#f2460d",
                "background-light": "#f8f6f5",
                "background-dark": "#0a0a0a",
            },
            fontFamily: {
                "display": ["Inter", "sans-serif"]
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
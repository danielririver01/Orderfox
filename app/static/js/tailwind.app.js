window.tailwind = window.tailwind || {};
window.tailwind.config = {
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                "primary": "#f97316",
                "accent-cyan": "#06b6d4",
                "accent-purple": "#a855f7",
                "bg-deep": "#050505",
                "surface": "#0f0f10",
                "surface-hover": "#161618",
                "border-subtle": "rgba(255, 255, 255, 0.05)",
                "text-muted": "#a1a1aa",
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
                heading: ['Outfit', 'sans-serif'],
            },
            backdropBlur: {
                xs: '2px',
            }
        },
    },
}

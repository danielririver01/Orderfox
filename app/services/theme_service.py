"""
theme_service.py — Temas de marca para el menú público.

Los temas son acentos predefinidos (hex) que garantizan pasar la validación
de contraste WCAG de brand.ts (astro/src/lib/brand.ts). Se guardan en la
columna existente `restaurants.brand_color` como un hex, por lo que NO se
requiere migración ni cambio de esquema.

Permisos por plan:
    - Emprendedor:  solo color por defecto (naranja Velzia).
    - Crecimiento:  8 temas predefinidos (sin hex libre).
    - Élite / Trial: temas predefinidos + color personalizado (hex libre).
"""

from app.utils.subscription import get_plan_limits

# Color por defecto (mismo que brand.ts BRAND_FALLBACK).
DEFAULT_BRAND_COLOR = '#FF7A29'

# 8 temas predefinidos. Cada hex pasó la validación de contrastRatio de
# brand.ts (>= 4.5:1 con el fondo oscuro del menú) — no cambies ninguno sin
# validarlo primero con resolveBrandColor, o el menú lo reemplazaría por
# el naranja por defecto.
BRAND_THEMES = [
    {'key': 'velzia',    'name': 'Naranja Velzia', 'hex': '#FF7A29'},
    {'key': 'rojo',      'name': 'Rojo',           'hex': '#E5484D'},
    {'key': 'verde',     'name': 'Verde',          'hex': '#30A46C'},
    {'key': 'azul',      'name': 'Azul',           'hex': '#2563EB'},
    {'key': 'morado',    'name': 'Morado',         'hex': '#7C3AED'},
    {'key': 'rosa',      'name': 'Rosa',           'hex': '#EC4899'},
    {'key': 'ambar',     'name': 'Ámbar',          'hex': '#F59E0B'},
    {'key': 'turquesa',  'name': 'Turquesa',       'hex': '#0EA5E9'},
]

# Mapa hex -> key para detectar si un valor enviado corresponde a un tema.
_THEME_HEX_TO_KEY = {theme['hex'].lower(): theme['key'] for theme in BRAND_THEMES}


def get_branding_permissions(plan_type):
    """
    Devuelve los permisos de personalización de marca para un plan.

    Returns:
        dict con:
            - themes_allowed (bool): ¿puede usar los temas predefinidos?
            - custom_allowed (bool): ¿puede elegir un hex libre (personalizado)?
    """
    limits = get_plan_limits(plan_type)
    return {
        'themes_allowed': bool(limits.get('brand_themes', False)),
        'custom_allowed': bool(limits.get('brand_custom_color', False)),
    }


def theme_for_color(brand_color):
    """
    Devuelve el tema (dict) que coincide con un hex, o None si no es un tema.
    Case-insensitive y tolera formato '#RRGGBB'.
    """
    if not brand_color:
        return None
    normalized = brand_color.strip().lower()
    key = _THEME_HEX_TO_KEY.get(normalized)
    if not key:
        return None
    return next((t for t in BRAND_THEMES if t['key'] == key), None)

"""
cover_bank — Banco curado de portadas por defecto para el menú público.

Cuando un restaurante no ha subido su propia portada (cover_image), el backend
resuelve una URL del banco según su `cuisine_type`. Nunca se devuelve null.

Reglas:
- `resolve_cover(restaurant)` es la única fuente de verdad: cover propia →
  banco por cuisine_type → default general.
- El banco es contenido curado por el equipo (git), no una tabla DB. Para
  cambiar una portada se edita la URL aquí (revisable en PR).
- v1: URLs de Unsplash estables (uso libre), sin subir nada a Cloudinary.
  Cloudinary entra cuando el restaurante sube su propia foto.
"""
import hashlib

# Tipos de cocina soportados por el banco. 'general' es el catch-all.
# Es también el vocabulario válido para `Restaurant.cuisine_type`.
CUISINE_TYPES = (
    'colombiana',
    'parrilla',
    'mariscos',
    'italiana',
    'arabe',
    'americana',
    'cafe_postres',
    'vegana',
    'general',
)

_UNSPLASH = (
    'https://images.unsplash.com/photo-{id}?q=80&w=1600&auto=format&fit=crop'
)

# Portadas curadas por tipo de cocina. URLs estables y con uso libre.
COVER_BANK = {
    'colombiana': _UNSPLASH.format(id='1555939594-58d7cb561ad1'),
    'parrilla': _UNSPLASH.format(id='1544025162-d76694265947'),
    'mariscos': _UNSPLASH.format(id='1559847844-5315695dadae'),
    'italiana': _UNSPLASH.format(id='1621996346565-e3dbc646d9a9'),
    'arabe': _UNSPLASH.format(id='1547592180-85f173990554'),
    'americana': _UNSPLASH.format(id='1568901346375-23c9450c58cd'),
    'cafe_postres': _UNSPLASH.format(id='1495474472287-4d71bcdd2085'),
    'vegana': _UNSPLASH.format(id='1512621776951-a57141f2eefd'),
    'general': _UNSPLASH.format(id='1517248135467-4c7edcad34c4'),
}

DEFAULT_COVER = COVER_BANK['general']


def resolve_cover(restaurant):
    """
    Devuelve la URL de portada del restaurante, nunca None.

    Jerarquía: cover propia → banco por cuisine_type → default 'general'.
    Un cuisine_type desconocido cae a 'general' (nunca 500).
    """
    if restaurant and getattr(restaurant, 'cover_image', None):
        return restaurant.cover_image
    cuisine = getattr(restaurant, 'cuisine_type', None) if restaurant else None
    return COVER_BANK.get(cuisine, DEFAULT_COVER)


def brand_color_or_default(restaurant):
    """
    Devuelve el brand_color del restaurante validado como hex (#RRGGBB),
    o None si no existe / no es válido. El frontend decide el fallback.
    """
    color = getattr(restaurant, 'brand_color', None) if restaurant else None
    if color and isinstance(color, str):
        candidate = color.strip()
        if len(candidate) == 7 and candidate[0] == '#':
            try:
                int(candidate[1:], 16)
                return candidate
            except ValueError:
                return None
    return None


def cuisine_hash(cuisine_type):
    """
    Digest determinista del cuisine_type (utilidad para tests / debugging).
    """
    if not cuisine_type:
        return None
    return hashlib.sha1(cuisine_type.encode('utf-8')).hexdigest()[:8]
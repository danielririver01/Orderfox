"""
Registro centralizado de verticales (mundos) del SaaS.

El selector post-registro (`/register/vertical`) se construye SOLO desde
aquí: agregar el 3er/4º mundo es añadir una entrada + su ruta de setup.
Nada de condicionales regados por `auth.py`.

Campos por vertical:
- slug: identificador estable (va a `businesses.vertical` / sesión).
- nombre / icono (material-symbols) / descripcion: lo que ve el usuario.
- setup_route: endpoint Flask de su setup (debe existir si enabled=True).
- enabled: False = tarjeta "Próximamente", sin link.
"""

VERTICALS = [
    {
        'slug': 'restaurant',
        'nombre': 'Restaurante',
        'icono': 'restaurant',
        'descripcion': 'Menú digital con QR, pedidos a WhatsApp, caja y Copilot VZ.',
        'setup_route': 'auth.setup_account',
        'enabled': True,
    },
    {
        'slug': 'verduras',
        'nombre': 'Verdurería',
        'icono': 'nutrition',
        'descripcion': 'POS de mostrador con PIN, inventario por kilos y control de merma.',
        'setup_route': 'auth.register_verduras',
        'enabled': True,
    },
    {
        'slug': 'delivery',
        'nombre': 'Delivery',
        'icono': 'delivery_dining',
        'descripcion': 'Reparto propio con zonas, tarifas y seguimiento de pedidos.',
        'setup_route': None,
        'enabled': False,
    },
    {
        'slug': 'farmacia',
        'nombre': 'Farmacia',
        'icono': 'medication',
        'descripcion': 'Catálogo por laboratorio, control de recetas e inventario.',
        'setup_route': None,
        'enabled': False,
    },
]

DEFAULT_VERTICAL = 'restaurant'


def get_vertical(slug):
    """Entrada del registro por slug, o None si no existe."""
    for v in VERTICALS:
        if v['slug'] == slug:
            return v
    return None


def get_enabled_vertical(slug):
    """Entrada solo si existe Y está habilitada (para el fork de registro)."""
    v = get_vertical(slug)
    if v and v['enabled'] and v['setup_route']:
        return v
    return None


def user_has_tenant(user):
    """True si el usuario ya configuró un negocio (cualquier vertical).

    Condición de acceso explícita del selector: con tenant → dashboard,
    sin tenant → selector. Cubre restaurante (restaurant_id) y verticales
    directos (Business propio como owner).
    """
    if user is None:
        return True
    if getattr(user, 'restaurant_id', None):
        return True
    from app.models import Business
    return Business.query.filter_by(owner_user_id=user.id).first() is not None

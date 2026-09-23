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
        'descripcion': 'Organiza tu menú, recibe pedidos y administra tu restaurante desde un solo lugar.',
        'setup_route': 'auth.setup_account',
        'enabled': True,
    },
    {
        'slug': 'verduras',
        'nombre': 'Verdurería',
        'icono': 'nutrition',
        'descripcion': 'Controla tus productos, ventas e inventario y mantén todo en orden fácilmente.',
        'setup_route': 'auth.register_verduras',
        'enabled': True,
    },
    # NOTA PRODUCTO (2026-09-22): Delivery NO es mundo del core Velzia.
    # Su tarjeta se eliminó del selector a propósito; su destino se definirá
    # después. No re-agregar aquí sin confirmación del dueño.
    {
        'slug': 'farmacia',
        'nombre': 'Farmacia',
        'icono': 'medication',
        'descripcion': 'Administra tus productos, ventas e inventario desde un solo lugar.',
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


def subscription_chip(status):
    """(etiqueta, color) del estado de suscripción para chips de tarjeta.

    Única fuente del mapeo estado → chip: el selector de mundos y
    cualquier superficie futura la reutilizan (no duplicar lógica).
    Color ('green'|'amber'|'red'|'gray') + etiqueta; los estados se
    indican con icono+texto en el template (no solo color).
    """
    s = status.get('status')
    if status.get('is_active') and s in ('active', 'cancellation_pending'):
        return 'Activo', 'green'
    if s == 'pending_payment':
        return 'Esperando pago', 'amber'
    if s and s.startswith('expiring_soon'):
        return 'Vence pronto', 'amber'
    if s == 'grace_period':
        return 'En período de gracia', 'amber'
    if s in ('expired', 'dormant'):
        return 'Pausado', 'red'
    return (s or '—'), 'gray'


def build_user_worlds(user):
    """Mundos activados del dueño, con estado de suscripción y entrada.

    Única fuente de la lista de mundos (regla del repo: no duplicar):
    - dashboard.mundos (Hub/redirect), el World Switcher y el modo hub
      del selector la consumen directa o indirectamente.
    - `chip_label`/`chip_color` salen de subscription_chip(); `message`
      es el texto de ayuda del estado (ej. "Vence en 20 días").
    - `entry_url` None = vertical con mundo creado pero sin frontend aún.
    """
    from flask import url_for

    from app.models import Business
    from app.utils.subscription import (
        get_business_subscription_status,
        get_subscription_status,
    )

    if user is None:
        return []

    worlds = []
    if user.restaurant is not None:
        r = user.restaurant
        status = get_subscription_status(r)
        chip_label, chip_color = subscription_chip(status)
        worlds.append({
            'kind': 'restaurant',
            'vertical_label': 'Restaurante',
            'icon': 'restaurant',
            'name': r.name,
            'slug': r.slug,
            'is_active': bool(r.is_active),
            'chip_label': chip_label,
            'chip_color': chip_color,
            'message': status.get('message'),
            'entry_url': url_for('dashboard.index'),
        })

    owned = Business.query.filter(
        Business.owner_user_id == user.id,
        Business.vertical != 'restaurant',
    ).order_by(Business.created_at.asc()).all()
    for b in owned:
        status = get_business_subscription_status(b)
        chip_label, chip_color = subscription_chip(status)
        entry = None
        if b.vertical == 'verduras':
            # Handoff: core emite el token SSO y redirige al POS.
            entry = url_for('dashboard.mundos_pos', slug=b.slug)
        worlds.append({
            'kind': 'business',
            'vertical_label': b.vertical.capitalize(),
            'icon': ('nutrition' if b.vertical == 'verduras' else 'storefront'),
            'name': b.name,
            'slug': b.slug,
            'is_active': bool(b.is_active),
            'chip_label': chip_label,
            'chip_color': chip_color,
            'message': status.get('message'),
            'entry_url': entry,
        })
    return worlds


def post_login_target(user):
    """Destino único tras iniciar sesión (regla del Multi-Mundos).

    Con mundo configurado → el SELECTOR de mundos en su modo hub (tarjetas
    con estado + agregar según plan). Sin mundo → selector en modo registro.
    Un solo lugar: /, login (GET/POST), sync-clerk y los guards del selector
    delegan aquí — el destino nunca se duplica por ruta.
    """
    if user is None:
        return 'auth.login'
    return 'auth.register_vertical'


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

from datetime import datetime, timedelta, timezone

from flask import current_app

from app.models import AITokenTransaction, AITokenWallet, Product, db

PLAN_LIMITS = {
    'emprendedor': {
        'max_worlds': 2,      # Ecosistema Multi-Mundos: mundos incluidos
        'max_products': 25,
        'max_employees': 1,   # v2.1.0: empleados (cashier/waiter) por plan
        'has_qr': True,
        'has_table_qr': False,
        'has_modifiers': False,
        'has_status_management': True,
        'has_ai_tokens': True,
        'brand_themes': False,
        'brand_custom_color': False,
        'name': 'Emprendedor',
        'price_cop': 30000,
        'duration_days': 30
    },
    'crecimiento': {
        'max_worlds': 4,      # Ecosistema Multi-Mundos: mundos incluidos
        'max_products': 100,
        'max_employees': 5,
        'has_qr': True,
        'has_table_qr': True,
        'has_modifiers': False,
        'has_status_management': True,
        'has_ai_tokens': True,
        'brand_themes': True,
        'brand_custom_color': False,
        'name': 'Crecimiento',
        'price_cop': 40000,
        'duration_days': 30
    },
    'elite': {
        'max_worlds': None,   # None = mundos ilimitados
        'max_products': float('inf'),
        'max_employees': None,  # None = ilimitado
        'has_qr': True,
        'has_table_qr': True,
        'has_modifiers': True,
        'has_status_management': True,
        'has_ai_tokens': True,
        'brand_themes': True,
        'brand_custom_color': True,
        'name': 'Élite',
        'price_cop': 50000,
        'duration_days': 30
    },
    'trial': {
        'max_worlds': 2,      # Decisión de producto: trial con límites
        'max_products': float('inf'),
        'max_employees': None,  # None = ilimitado
        'has_qr': True,
        'has_table_qr': True,
        'has_modifiers': True,
        'has_status_management': True,
        'has_ai_tokens': True,
        'brand_themes': True,
        'brand_custom_color': True,
        'name': 'Prueba Premium · 60 días',
        'price_cop': 0,
        'duration_days': 60
    }
}

# ─── Velzia 2.0.0: Configuración de Tokens IA ─────────────────────────────────

# Límites de tokens asignados por plan mensualmente
AI_TOKEN_LIMITS = {
    'trial':       50,
    'emprendedor': 150,
    'crecimiento': 400,
    'elite':       1000,
}

# Paquetes de recarga (Top-ups) — Copilot VZ / Scanner IA
TOP_UP_PACKS = {
    '25': {
        'price_cop': 5000,
        'tokens': 25,
        'label': 'Pack Inicial',
        'badge': 'Starter'
    },
    '50': {
        'price_cop': 9000,
        'tokens': 50,
        'label': 'Pack Popular',
        'badge': 'Más popular'
    },
    '100': {
        'price_cop': 16000,
        'tokens': 100,
        'label': 'Pack Pro',
        'badge': 'Mejor valor'
    },
}

GRACE_PERIOD_DAYS = 5

# Estados de suscripción de un Business (vertical directo). Misma semántica
# que Restaurant.subscription_state: 'active' | 'dormant' | 'cancellation_pending'.
BUSINESS_SUBSCRIPTION_STATES = ('active', 'dormant', 'cancellation_pending')


# ─── Billing unificado (Ecosistema Multi-Mundos) ────────────────────────────
# El User dueño es la ÚNICA fuente de verdad del billing: un pago cubre todos
# sus mundos. Las columnas de Restaurant/Business pasan a ser caché de
# legibilidad. Regla de compatibilidad: si el dueño aún no tiene datos de
# billing, el subject se gobierna con sus columnas locales — los tenants
# legacy (piloto, API, datos viejos) siguen funcionando idéntico que siempre.

def _resolve_owner(subject):
    """User dueño del subject (Restaurant o Business), o None."""
    from app.models import User
    if subject is None:
        return None
    owner_id = getattr(subject, 'owner_user_id', None)
    if owner_id:
        return db.session.get(User, owner_id)
    if type(subject).__name__ == 'Restaurant':
        return (User.query.filter_by(restaurant_id=subject.id, role='owner')
                .order_by(User.id.asc()).first())
    return None


def _owner_carries_billing(owner):
    """True si el dueño YA tiene datos de billing (goberna sus mundos).

    Un User recién creado (trial, sin fecha, active, sin trial usado) NO
    goberna: el subject usa sus columnas locales hasta que exista un ciclo
    propagado (pago, trial, dormido)."""
    return bool(
        getattr(owner, 'subscription_expires_at', None)
        or getattr(owner, 'has_used_trial', False)
        or (getattr(owner, 'subscription_state', 'active') or 'active') != 'active'
    )


def _billing_view_for(subject):
    """Snapshot de billing para leer: desde el User dueño (fuente única) o
    desde las columnas locales del subject (legacy). Expone la misma interfaz
    (plan_type, subscription_expires_at, subscription_state, is_active) que
    las funciones de status ya conocen.

    is_active conjuga la bandera del dueño y la del subject: la suspensión
    administrativa de un mundo o una cuenta pausada bloquean, cada una por
    su lado (un mundo pending_payment nunca se abre aunque la cuenta esté
    activa)."""
    from types import SimpleNamespace
    owner = _resolve_owner(subject)
    if owner is not None and _owner_carries_billing(owner):
        return SimpleNamespace(
            plan_type=owner.plan_type or 'trial',
            subscription_expires_at=owner.subscription_expires_at,
            subscription_state=owner.subscription_state or 'active',
            is_active=(bool(owner.is_active)
                       and bool(getattr(subject, 'is_active', True))),
        )
    return SimpleNamespace(
        plan_type=getattr(subject, 'plan_type', None) or 'trial',
        subscription_expires_at=getattr(subject, 'subscription_expires_at', None),
        subscription_state=getattr(subject, 'subscription_state', None) or 'active',
        is_active=bool(getattr(subject, 'is_active', True)),
    )


def propagate_billing_up(subject):
    """Copia el billing del subject (Restaurant/Business) a su User dueño y
    sincroniza hacia abajo el resto de mundos del dueño (cachés de lectura).

    - Sin dueño: no-op (regla de oro legacy: cada fila se gobierna sola).
    - El trial de un dueño que ya lo usó NO se extiende al añadir mundos:
      el ciclo es del usuario (un solo reloj), no de cada fila.
    - No hace commit: se integra en la transacción del llamador."""
    owner = _resolve_owner(subject)
    if owner is None:
        return None
    is_trial_row = (getattr(subject, 'plan_type', None) == 'trial')
    if not (is_trial_row and owner.has_used_trial):
        owner.plan_type = (getattr(subject, 'plan_type', None)
                           or owner.plan_type)
        if getattr(subject, 'subscription_expires_at', None) is not None:
            owner.subscription_expires_at = subject.subscription_expires_at
    owner.subscription_state = (getattr(subject, 'subscription_state', None)
                                or 'active')
    if getattr(subject, 'has_used_trial', False):
        owner.has_used_trial = True
    _sync_billing_down(owner, exclude_id=getattr(subject, 'id', None))
    return owner


def _sync_billing_down(owner, exclude_id=None, set_active=None):
    """Replica el billing del dueño a sus filas (cachés): su restaurante y
    todos los businesses que posee. Los writes de ciclo (pago, dormido)
    llegan a un subject y de aquí saltan a los demás mundos.

    set_active (opcional): además sincroniza la bandera `is_active` de las
    filas — True al activar/reactivar la cuenta, False al pausarla. None
    (default) deja `is_active` intacto: el estado de suscripción se
    propaga, el apagón administrativo de una fila concreta no se pisa."""
    from app.models import Business, Restaurant
    plan = owner.plan_type
    expires = owner.subscription_expires_at
    state = owner.subscription_state or 'active'
    if owner.restaurant_id:
        r = db.session.get(Restaurant, owner.restaurant_id)
        if r is not None and r.id != exclude_id:
            r.plan_type = plan
            r.subscription_expires_at = expires
            r.subscription_state = state
            if set_active is not None:
                r.is_active = bool(set_active)
    owned = Business.query.filter(Business.owner_user_id == owner.id).all()
    for b in owned:
        if b.id == exclude_id:
            continue
        b.plan_type = plan
        b.subscription_expires_at = expires
        b.subscription_state = state
        if set_active is not None:
            b.is_active = bool(set_active)


def count_user_worlds(user):
    """Mundos en uso de un dueño: su restaurante (si tiene) + sus verticales
    directos. Los espejos de restaurantes NO suman doble."""
    from app.models import Business
    if user is None:
        return 0
    count = Business.query.filter(
        Business.owner_user_id == user.id,
        Business.vertical != 'restaurant',
    ).count()
    if user.restaurant_id:
        count += 1
    return count


_NEXT_TIER = {'trial': 'Crecimiento', 'emprendedor': 'Crecimiento',
              'crecimiento': 'Élite'}


def can_activate_vertical(user):
    """¿Puede el dueño activar OTRO mundo según su plan?

    Returns (ok, info): info trae max_worlds/current_worlds y, si está
    bloqueado, plan_name + upgrade_to para el mensaje de upgrade."""
    if user is None:
        return False, {}
    limits = get_plan_limits(getattr(user, 'plan_type', None) or 'trial')
    max_worlds = limits.get('max_worlds')
    current = count_user_worlds(user)
    info = {'max_worlds': max_worlds, 'current_worlds': current}
    if max_worlds is None or current < max_worlds:
        return True, info
    info['plan_name'] = limits.get('name')
    info['upgrade_to'] = _NEXT_TIER.get(getattr(user, 'plan_type', None))
    return False, info


def vertical_quota_message(info):
    """Mensaje de upgrade para el flash cuando can_activate_vertical
    bloquea. Un solo texto para servicio y rutas (no duplicar lógica)."""
    max_w = info.get('max_worlds')
    current = info.get('current_worlds', '?')
    plan_name = info.get('plan_name') or 'actual'
    base = (f'Tu plan {plan_name} incluye {max_w} mundo(s) y ya tienes '
            f'{current} activos.')
    upgrade_to = info.get('upgrade_to')
    if upgrade_to:
        return base + f' Sube al plan {upgrade_to} para activar más mundos.'
    return base + ' Revisa tus mundos activos o contacta soporte.'


def is_subscription_active(restaurant, include_grace_period=False):
    """
    Verifica centralmente si una suscripción está activa y no ha expirado.
    SIEMPRE usa la hora del servidor en UTC.
    
    Args:
        restaurant: Objeto Restaurant
        include_grace_period (bool): Si es True, permite el acceso durante los 10 días post-expiración.
        
    Returns:
        bool: True si la suscripción es válida (o está en gracia si se solicita)
    """
    if not restaurant:
        return False

    # Billing unificado: resuelve desde el User dueño (fuente única) o desde
    # las columnas locales si el tenant es legacy (regla de oro).
    view = _billing_view_for(restaurant)
    if not view.is_active:
        return False

    if not view.subscription_expires_at:
        return False

    expires_at = view.subscription_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    
    
    if expires_at > now:
        return True
    if include_grace_period:
        grace_end = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
        return now <= grace_end

    return False


def can_buy_tokens(restaurant):
    """
    ¿El restaurante puede COMPRAR créditos IA ahora?
    Solo si la suscripción está estrictamente activa (trial o plan de pago).
    En periodo de gracia o expirada → NO puede comprar (debe activar un plan).
    """
    return is_subscription_active(restaurant, include_grace_period=False)


def can_use_ai(restaurant):
    """
    ¿El restaurante puede USAR la IA (Copilot VZ / Scanner IA) ahora?
    Sí si está activa O en periodo de gracia. Tras la gracia → bloqueado,
    aunque tenga créditos comprados (quedan congelados hasta activar plan).
    """
    return is_subscription_active(restaurant, include_grace_period=True)


def get_plan_limits(plan_type):
    return PLAN_LIMITS.get(plan_type, PLAN_LIMITS['emprendedor'])

def check_feature_access(restaurant, feature):
    if not restaurant:
        return False

    if not is_subscription_active(restaurant):
        return False

    limits = get_plan_limits(_billing_view_for(restaurant).plan_type)
    return limits.get(feature, False)

def check_product_limit(restaurant):
    if not restaurant:
        return False, "Restaurante no encontrado"
    
    if not is_subscription_active(restaurant):
        return False, "Tu suscripción ha expirado. Renueva tu plan para continuar."
    
    limits = get_plan_limits(_billing_view_for(restaurant).plan_type)
    max_products = limits['max_products']
    
    if max_products == float('inf'):
        return True, "Productos ilimitados"

    current_active_count = Product.query.filter_by(restaurant_id=restaurant.id, is_active=True).count()
    
    if current_active_count >= max_products:
        return False, f"Has alcanzado el límite de {max_products} productos activos de tu plan {limits['name']}."
    
    remaining = max_products - current_active_count
    return True, f"Te quedan {remaining} producto{'s' if remaining != 1 else ''} disponible{'s' if remaining != 1 else ''}."

def get_subscription_status(restaurant):
    if not restaurant:
        return {
            'is_active': False,
            'status': 'not_found',
            'message': 'Restaurante no encontrado',
            'can_crud': False,
            'badge_class': 'bg-gray-100 text-gray-600',
            'badge_text': 'No encontrado',
            'plan': None
        }

    # Billing unificado: la fuente de verdad es el User dueño (o columnas
    # locales si el tenant es legacy). El resto de la función no cambia.
    restaurant = _billing_view_for(restaurant)

    if not restaurant.is_active:
        if restaurant.subscription_state == 'dormant':
            return {
                'is_active': False,
                'status': 'dormant',
                'message': '¡Hola de nuevo! Tus menús, ventas y reportes están guardados de forma segura. '
                           'Reactivá tu plan en 1 clic para continuar operando.',
                'can_crud': False,
                'badge_class': 'bg-blue-100 text-blue-700',
                'badge_text': 'Reactivar',
                'plan': restaurant.plan_type
            }
        return {
            'is_active': False,
            'status': 'inactive',
            'message': 'Cuenta suspendida administrativamente',
            'can_crud': False,
            'badge_class': 'bg-red-100 text-red-600',
            'badge_text': 'Suspendida',
            'plan': restaurant.plan_type
        }

    if restaurant.subscription_state == 'cancellation_pending':
        expires_at = restaurant.subscription_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        meses_es = {
            1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
            5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
            9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
        }
        if expires_at and expires_at > now:
            formatted_expiration = f"{expires_at.day} de {meses_es[expires_at.month]} de {expires_at.year}"
            return {
                'is_active': True,
                'status': 'cancellation_pending',
                'expires_at': expires_at,
                'formatted_expiration': formatted_expiration,
                'can_crud': True,
                'message': f'Tu suscripción está cancelada y vencerá el {formatted_expiration}. '
                           'Puedes seguir usando el sistema hasta entonces.',
                'badge_class': 'bg-amber-100 text-amber-700',
                'badge_text': 'Cancelación pendiente',
                'plan': restaurant.plan_type
            }
        return {
            'is_active': False,
            'status': 'dormant',
            'message': 'Tu suscripción ha vencido. Reactiva tu plan para continuar.',
            'can_crud': False,
            'badge_class': 'bg-blue-100 text-blue-700',
            'badge_text': 'Reactivar',
            'plan': restaurant.plan_type
        }

    if not restaurant.subscription_expires_at:
        return {
            'is_active': False,
            'status': 'no_subscription',
            'message': 'No tienes una suscripción activa',
            'can_crud': False,
            'badge_class': 'bg-yellow-100 text-yellow-600',
            'badge_text': 'Sin suscripción',
            'plan': restaurant.plan_type
        }
    
    expires_at = restaurant.subscription_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    
    delta = expires_at - now
    total_seconds = delta.total_seconds()
    
    days_remaining = int(total_seconds / 86400)
    if total_seconds % 86400 > 0 and total_seconds > 0:
        days_remaining += 1
    
    meses_es = {
        1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
        5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
        9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
    }
    formatted_expiration = f"{expires_at.day} de {meses_es[expires_at.month]} de {expires_at.year}"
    
    if total_seconds > 0:
        if 5 <= days_remaining <= 7:
            return {
                'is_active': True,
                'status': 'expiring_soon_neutral',
                'days_remaining': days_remaining,
                'expires_at': expires_at,
                'formatted_expiration': formatted_expiration,
                'can_crud': True,
                'message': f'Tu acceso a la plataforma vence en {days_remaining} días. Renueva hoy y evita la suspensión de tu menú digital.',
                'badge_class': 'bg-gray-100 text-gray-700',
                'badge_text': 'Vence pronto',
                'plan': restaurant.plan_type
            }
        elif 2 <= days_remaining <= 4:
            return {
                'is_active': True,
                'status': 'expiring_soon_warning',
                'days_remaining': days_remaining,
                'expires_at': expires_at,
                'formatted_expiration': formatted_expiration,
                'can_crud': True,
                'message': f'Evita interrupciones en tu menú digital. Tu suscripción vence en {days_remaining} días.',
                'badge_class': 'bg-indigo-100 text-indigo-700',
                'badge_text': 'Renovar pronto',
                'plan': restaurant.plan_type
            }
        elif days_remaining == 1:
            return {
                'is_active': True,
                'status': 'expiring_soon_urgent',
                'days_remaining': days_remaining,
                'expires_at': expires_at,
                'formatted_expiration': formatted_expiration,
                'can_crud': True,
                'message': '¡Tu menú digital dejará de recibir pedidos mañana! Renueva ahora para evitar el bloqueo.',
                'badge_class': 'bg-orange-100 text-orange-700',
                'badge_text': 'Vence mañana',
                'plan': restaurant.plan_type
            }
        
        return {
            'is_active': True,
            'status': 'active',
            'days_remaining': days_remaining,
            'expires_at': expires_at,
            'formatted_expiration': formatted_expiration,
            'can_crud': True,
            'message': f'Suscripción activa. {days_remaining} día{"s" if days_remaining != 1 else ""} restante{"s" if days_remaining != 1 else ""}.',
            'badge_class': 'bg-green-100 text-green-700',
            'badge_text': 'Activa',
            'plan': restaurant.plan_type
        }
    
    grace_end = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
    
    if now <= grace_end:
        grace_delta = grace_end - now
        days_grace_remaining = int(grace_delta.total_seconds() / 86400)
        if grace_delta.total_seconds() % 86400 > 0:
            days_grace_remaining += 1
        
        return {
            'is_active': False,
            'status': 'grace_period',
            'days_remaining': days_remaining,
            'days_grace_remaining': days_grace_remaining,
            'expires_at': expires_at,
            'formatted_expiration': formatted_expiration,
            'can_crud': False,
            'message': f'Tu suscripción ha finalizado. Tus datos están seguros. Tienes {days_grace_remaining} día{"s" if days_grace_remaining != 1 else ""} de gracia para renovar y seguir gestionando tu restaurante.',
            'badge_class': 'bg-orange-100 text-orange-700',
            'badge_text': 'Periodo de gracia',
            'plan': restaurant.plan_type
        }
    
    days_since_expiration = abs(days_remaining)
    
    return {
        'is_active': False,
        'status': 'expired',
        'days_remaining': days_remaining,
        'days_since_expiration': days_since_expiration,
        'expires_at': expires_at,
        'formatted_expiration': formatted_expiration,
        'can_crud': False,
        'message': f'Suscripción expirada hace {days_since_expiration} día{"s" if days_since_expiration != 1 else ""}. Renueva para continuar.',
        'badge_class': 'bg-red-100 text-red-700',
        'badge_text': 'Expirada',
        'plan': restaurant.plan_type
    }

def get_business_subscription_status(business):
    """Estado de suscripción de un Business (vertical directo) — misma
    máquina de estados que `get_subscription_status(restaurant)`, leyendo
    `businesses` (owner/plan/expires/state propio). Los espejos de
    restaurantes siguen usando `get_subscription_status`.

    Diferencia con el de restaurantes: NO consulta `restaurant.plan_type`
    ni variables de restaurante; todo sale del Business. Mensajes en
    lenguaje de verdulero ("tu puesto", "tu negocio").
    """
    if not business:
        return {
            'is_active': False, 'status': 'not_found',
            'message': 'Negocio no encontrado', 'can_crud': False,
            'badge_class': 'bg-gray-100 text-gray-600',
            'badge_text': 'No encontrado', 'plan': None,
        }

    # Billing unificado: la fuente de verdad es el User dueño (o columnas
    # locales si el tenant es legacy). El resto de la función no cambia.
    business = _billing_view_for(business)

    now = datetime.now(timezone.utc)

    if not business.is_active:
        if getattr(business, 'subscription_state', None) == 'dormant':
            return {
                'is_active': False, 'status': 'dormant',
                'message': ('¡Hola de nuevo! Tus productos, ventas y reportes '
                            'están guardados. Reactiva tu plan para seguir '
                            'vendiendo.'),
                'can_crud': False,
                'badge_class': 'bg-blue-100 text-blue-700',
                'badge_text': 'Reactivar', 'plan': business.plan_type,
            }
        # Plan pago aún sin pagar (alta con plan != trial): pendiente de
        # pago, NO suspendida administrativamente.
        return {
            'is_active': False, 'status': 'pending_payment',
            'message': ('Elige tu plan y realiza el pago para activar tu '
                        'negocio.'),
            'can_crud': False,
            'badge_class': 'bg-yellow-100 text-yellow-600',
            'badge_text': 'Pago pendiente', 'plan': business.plan_type,
        }

    if getattr(business, 'subscription_state', None) == 'cancellation_pending':
        expires_at = business.subscription_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at > now:
            meses_es = {1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                        5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                        9: 'septiembre', 10: 'octubre', 11: 'noviembre',
                        12: 'diciembre'}
            formatted = (f"{expires_at.day} de {meses_es[expires_at.month]} "
                         f"de {expires_at.year}")
            return {
                'is_active': True, 'status': 'cancellation_pending',
                'expires_at': expires_at,
                'formatted_expiration': formatted,
                'can_crud': True,
                'message': (f'Tu suscripción está cancelada y vencerá el '
                            f'{formatted}. Puedes seguir vendiendo hasta '
                            'entonces.'),
                'badge_class': 'bg-amber-100 text-amber-700',
                'badge_text': 'Cancelación pendiente',
                'plan': business.plan_type,
            }
        return {
            'is_active': False, 'status': 'dormant',
            'message': 'Tu suscripción ha vencido. Reactiva tu plan para '
                       'seguir vendiendo.',
            'can_crud': False,
            'badge_class': 'bg-blue-100 text-blue-700',
            'badge_text': 'Reactivar', 'plan': business.plan_type,
        }

    if not business.subscription_expires_at:
        # Sin fecha de vencimiento = tenant legacy/onboarding asistido (piloto,
        # businesses creados vía API sin dueño): siguen operando como siempre
        # (backward-compatible — jamás bloquear ventas por un campo que nunca
        # se les asignó). Los self-service SIEMPRE tienen expiry (trial) o
        # quedan en pending_payment (plan pago sin pagar).
        return {
            'is_active': True, 'status': 'active',
            'can_crud': True,
            'message': 'Suscripción activa.',
            'badge_class': 'bg-green-100 text-green-700',
            'badge_text': 'Activa', 'plan': business.plan_type,
        }

    expires_at = business.subscription_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    delta = expires_at - now
    total_seconds = delta.total_seconds()

    days_remaining = int(total_seconds / 86400)
    if total_seconds % 86400 > 0 and total_seconds > 0:
        days_remaining += 1

    if total_seconds > 0:
        if 1 <= days_remaining <= 7:
            return {
                'is_active': True, 'status': 'expiring_soon',
                'days_remaining': days_remaining,
                'expires_at': expires_at,
                'can_crud': True,
                'message': (f'Tu plan vence en {days_remaining} día'
                            f'{"s" if days_remaining != 1 else ""}. '
                            'Renueva para no interrumpir tu POS.'),
                'badge_class': 'bg-amber-100 text-amber-700',
                'badge_text': 'Vence pronto', 'plan': business.plan_type,
            }
        return {
            'is_active': True, 'status': 'active',
            'days_remaining': days_remaining,
            'expires_at': expires_at,
            'can_crud': True,
            'message': (f'Suscripción activa. {days_remaining} día'
                        f'{"s" if days_remaining != 1 else ""} restante'
                        f'{"s" if days_remaining != 1 else ""}.'),
            'badge_class': 'bg-green-100 text-green-700',
            'badge_text': 'Activa', 'plan': business.plan_type,
        }

    grace_end = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
    if now <= grace_end:
        grace_delta = grace_end - now
        days_grace = int(grace_delta.total_seconds() / 86400)
        if grace_delta.total_seconds() % 86400 > 0:
            days_grace += 1
        return {
            'is_active': False, 'status': 'grace_period',
            'days_grace_remaining': days_grace,
            'expires_at': expires_at,
            'can_crud': False,
            'message': (f'Tu plan finalizó. Tus datos están seguros. Tienes '
                        f'{days_grace} día{"s" if days_grace != 1 else ""} '
                        'de gracia para renovar y seguir vendiendo.'),
            'badge_class': 'bg-orange-100 text-orange-700',
            'badge_text': 'Periodo de gracia', 'plan': business.plan_type,
        }

    days_since = abs(days_remaining)
    return {
        'is_active': False, 'status': 'expired',
        'days_since_expiration': days_since,
        'expires_at': expires_at,
        'can_crud': False,
        'message': (f'Suscripción expirada hace {days_since} día'
                    f'{"s" if days_since != 1 else ""}. Renueva para '
                    'seguir vendiendo.'),
        'badge_class': 'bg-red-100 text-red-700',
        'badge_text': 'Expirada', 'plan': business.plan_type,
    }


def can_perform_crud(restaurant):
    """
    Verifica si el restaurante tiene permisos de escritura (CRUD).
    Solo se permite si la suscripción está activa (no en gracia ni expirada).
    """
    if not restaurant: return False
    return is_subscription_active(restaurant, include_grace_period=False)


def sanitize_restaurant_limits(restaurant):
    """
    Aplica forzosamente los límites del plan actual al restaurante.
    """
    if not restaurant:
        return

    limits = get_plan_limits(_billing_view_for(restaurant).plan_type)
    max_products = limits.get('max_products', float('inf'))
    
    if max_products != float('inf'):
        active_products = Product.query.filter_by(
            restaurant_id=restaurant.id, 
            is_active=True
        ).order_by(Product.id.asc()).all()
        
        current_count = len(active_products)
        
        if current_count > max_products:
            excess_count = current_count - max_products
            
            products_to_deactivate = active_products[-excess_count:]
            
            for prod in products_to_deactivate:
                prod.is_active = False
            
            current_app.logger.info(f"SANEAMIENTO: Desactivados {len(products_to_deactivate)} productos por límite de plan.")

    if not limits.get('has_status_management', False):
        if not restaurant.is_open:
            restaurant.is_open = True
            current_app.logger.info("SANEAMIENTO: Restaurante forzado a ABIERTO por restricción de plan.")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR en sanitize_restaurant_limits: {e}")

def initialize_or_reset_token_wallet(user, is_reset=False, mp_payment_id=None):
    """
    Sincroniza el wallet de tokens IA con el plan actual del restaurante.
    Punto Central de Verdad para Velzia 2.0.0.
    """
    if not user or not user.restaurant:
        return None

    wallet = user.token_wallet
    # Billing unificado: el plan del dueño vive en el User si ya tiene ciclo
    # propio; fallback al restaurante (empleados, datos legacy).
    if _owner_carries_billing(user):
        plan_type = user.plan_type
    elif user.restaurant:
        plan_type = user.restaurant.plan_type
    else:
        plan_type = 'trial'
    
    # Importar los límites centrales de este MISMO archivo (subscription.py)
    plan_limit = AI_TOKEN_LIMITS.get(plan_type, 10)
    
    now = datetime.now(timezone.utc)
    
    # Helper para calcular fecha del próximo reset (1º del mes siguiente)
    def get_next_reset_date(current_date):
        if current_date.month == 12:
            return current_date.replace(year=current_date.year + 1, month=1, day=1,
                                       hour=0, minute=0, second=0, microsecond=0)
        return current_date.replace(month=current_date.month + 1, day=1,
                                   hour=0, minute=0, second=0, microsecond=0)

    # 1. Crear wallet si no existe (con lock pesimista para evitar duplicados)
    if not wallet:
        try:
            # Lock pesimista: si dos requests concurrentes intentan crear,
            # el segundo espera hasta que el primero termine.
            wallet = AITokenWallet.query.filter_by(user_id=user.id).with_for_update().first()
            if not wallet:
                is_trial_plan = (plan_type == 'trial')
                if is_trial_plan:
                    actual_plan_limit = plan_limit
                    actual_plan_tokens = plan_limit
                    reset_at = None
                else:
                    actual_plan_limit = plan_limit
                    actual_plan_tokens = plan_limit
                    reset_at = get_next_reset_date(now)

                wallet = AITokenWallet(
                    user_id=user.id,
                    plan_limit=actual_plan_limit,
                    plan_tokens=actual_plan_tokens,
                    extra_tokens=0,
                    tokens_used_month=0,
                    reset_at=reset_at
                )
                db.session.add(wallet)

                tx = AITokenTransaction(
                    user_id=user.id,
                    type='topup_plan',
                    amount=actual_plan_tokens,
                    source='system_init',
                    description=f'Wallet inicializado — Plan {plan_type}'
                )
                db.session.add(tx)
                db.session.commit()
                current_app.logger.info(f"WALLET: Creado para usuario {user.id} ({plan_type})")
        except Exception as e:
            db.session.rollback()
            wallet = AITokenWallet.query.filter_by(user_id=user.id).with_for_update().first()
            if not wallet:
                current_app.logger.error(f"ERROR CRÍTICO WALLET: No se pudo crear ni recuperar: {e}")
                return None
        return wallet

    # 2. Verificar Reset automático (si ya pasó la fecha de reset)
    if wallet.reset_at and now >= wallet.reset_at:
        is_reset = True
        current_app.logger.info(f"WALLET: Detectado reset automático necesario para {user.id}")

    # 3. Executar Reset (por renovación o cambio de mes)
    if is_reset:
        # IDEMPOTENCIA: Verificar si ya acreditamos este pago exacto
        if mp_payment_id:
            already = AITokenTransaction.query.filter_by(
                mp_payment_id=mp_payment_id, 
                type='topup_plan'
            ).first()
            if already:
                current_app.logger.info(f"WALLET: Pago {mp_payment_id} ya acreditado. Saltando reset.")
                return wallet

        # UPDATE atómico — evita lost updates entre requests concurrentes.
        # El SET usa valores calculados sin leer primero desde otra transacción.
        next_reset = get_next_reset_date(now if now >= (wallet.reset_at or now) else wallet.reset_at)
        AITokenWallet.query.filter_by(id=wallet.id).update({
            'plan_limit': plan_limit,
            'plan_tokens': plan_limit,
            'tokens_used_month': 0,
            'reset_at': next_reset,
        })

        tx = AITokenTransaction(
            user_id=user.id,
            type='topup_plan',
            amount=plan_limit,
            source='plan_renewal' if mp_payment_id else 'auto_reset',
            mp_payment_id=mp_payment_id,
            description=f'Reset de tokens ({plan_type})'
        )
        db.session.add(tx)
        db.session.commit()
        current_app.logger.info(f"WALLET: Reset completo para usuario {user.id}")

    return wallet
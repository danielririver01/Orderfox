from datetime import datetime, timezone
from app.models import db, Product

PLAN_LIMITS = {
    'emprendedor': {
        'max_products': 25,
        'has_qr': True,
        'has_table_qr': False,
        'has_modifiers': False,
        'has_status_management': False,
        'name': 'Emprendedor'
    },
    'crecimiento': {
        'max_products': 100,
        'has_qr': True,
        'has_table_qr': True,
        'has_modifiers': False,
        'has_status_management': True,
        'name': 'Crecimiento'
    },
    'elite': {
        'max_products': float('inf'),
        'has_qr': True,
        'has_table_qr': True,
        'has_modifiers': True,
        'has_status_management': True,
        'name': 'Élite'
    },
    'trial': {
        'max_products': float('inf'),
        'has_qr': True,
        'has_table_qr': True,
        'has_modifiers': True,
        'has_status_management': True,
        'name': 'Prueba Gratuita Premium'
    }
}

# ─── Velzia 2.0.0: Configuración de Tokens IA ─────────────────────────────────

# Límites de tokens asignados por plan mensualmente
AI_TOKEN_LIMITS = {
    'trial':       10,
    'emprendedor': 25,
    'crecimiento': 40,
    'elite':       None,  # NULL en DB = Ilimitado
}

# Paquetes de recarga (Top-ups)
TOP_UP_PACKS = {
    '5k':  {
        'price_cop': 5000, 
        'tokens': 15, 
        'label': 'Pack Básico',
        'badge': 'Starter'
    },
    '10k': {
        'price_cop': 10000, 
        'tokens': 35, 
        'label': 'Pack Pro',
        'badge': 'Popular'
    },
}

GRACE_PERIOD_DAYS = 10

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
    if not restaurant or not restaurant.is_active:
        return False
    
    if not restaurant.subscription_expires_at:
        return False
    
    expires_at = restaurant.subscription_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    
    
    if expires_at > now:
        return True
    if include_grace_period:
        from datetime import timedelta
        grace_end = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
        return now <= grace_end
        
    return False

def get_plan_limits(plan_type):
    return PLAN_LIMITS.get(plan_type, PLAN_LIMITS['emprendedor'])

def check_feature_access(restaurant, feature):
    if not restaurant:
        return False
    
    if not is_subscription_active(restaurant):
        return False
    
    limits = get_plan_limits(restaurant.plan_type)
    return limits.get(feature, False)

def check_product_limit(restaurant):
    if not restaurant:
        return False, "Restaurante no encontrado"
    
    if not is_subscription_active(restaurant):
        return False, "Tu suscripción ha expirado. Renueva tu plan para continuar."
    
    limits = get_plan_limits(restaurant.plan_type)
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
    
    if not restaurant.is_active:
        return {
            'is_active': False,
            'status': 'inactive',
            'message': 'Cuenta suspendida administrativamente',
            'can_crud': False,
            'badge_class': 'bg-red-100 text-red-600',
            'badge_text': 'Suspendida',
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
                'message': f'Tu acceso a Pedidos Digitales vence en {days_remaining} días. Mantén el control de tu negocio.',
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
    
    from datetime import timedelta
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
            'message': f'⚠️ Suscripción vencida. Tienes {days_grace_remaining} día{"s" if days_grace_remaining != 1 else ""} de gracia para renovar.',
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

    limits = get_plan_limits(restaurant.plan_type)
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
            
            print(f"SANEAMIENTO: Desactivados {len(products_to_deactivate)} productos por límite de plan.")

    if not limits.get('has_status_management', False):
        if not restaurant.is_open:
            restaurant.is_open = True
            print("SANEAMIENTO: Restaurante forzado a ABIERTO por restricción de plan.")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"ERROR en sanitize_restaurant_limits: {e}")

def initialize_or_reset_token_wallet(user, is_reset=False, mp_payment_id=None):
    """
    Sincroniza el wallet de tokens IA con el plan actual del restaurante.
    Punto Central de Verdad para Velzia 2.0.0.
    """
    from app.models import AITokenWallet, AITokenTransaction
    from datetime import datetime, timezone

    if not user or not user.restaurant:
        return None

    wallet = user.token_wallet
    plan_type = user.restaurant.plan_type
    
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

    # 1. Crear wallet si no existe
    if not wallet:
        wallet = AITokenWallet(
            user_id=user.id,
            plan_limit=plan_limit,
            plan_tokens=plan_limit if plan_limit is not None else 0,
            extra_tokens=0,
            tokens_used_month=0,
            reset_at=get_next_reset_date(now)
        )
        db.session.add(wallet)
        
        tx = AITokenTransaction(
            user_id=user.id,
            type='topup_plan',
            amount=plan_limit if plan_limit is not None else 0,
            source='system_init',
            description=f'Wallet inicializado — Plan {plan_type}'
        )
        db.session.add(tx)
        print(f"WALLET: Creado para usuario {user.id} ({plan_type})")
        return wallet

    # 2. Verificar Reset automático (si ya pasó la fecha de reset)
    if wallet.reset_at and now >= wallet.reset_at:
        is_reset = True
        print(f"WALLET: Detectado reset automático necesario para {user.id}")

    # 3. Executar Reset (por renovación o cambio de mes)
    if is_reset:
        # IDEMPOTENCIA: Verificar si ya acreditamos este pago exacto
        if mp_payment_id:
            already = AITokenTransaction.query.filter_by(
                mp_payment_id=mp_payment_id, 
                type='topup_plan'
            ).first()
            if already:
                print(f"WALLET: Pago {mp_payment_id} ya acreditado. Saltando reset.")
                return wallet

        wallet.plan_limit = plan_limit
        wallet.plan_tokens = plan_limit if plan_limit is not None else 0
        wallet.tokens_used_month = 0
        wallet.reset_at = get_next_reset_date(now if now >= (wallet.reset_at or now) else wallet.reset_at)

        tx = AITokenTransaction(
            user_id=user.id,
            type='topup_plan',
            amount=plan_limit if plan_limit is not None else 0,
            source='plan_renewal' if mp_payment_id else 'auto_reset',
            mp_payment_id=mp_payment_id,
            description=f'Reset de tokens ({plan_type})'
        )
        db.session.add(tx)
        db.session.commit()
        print(f"WALLET: Reset completo para usuario {user.id}")

    return wallet
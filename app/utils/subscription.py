from datetime import datetime, timezone
from app.models import db, Product

PLAN_LIMITS = {
    'emprendedor': {
        'max_products': 25,
        'has_qr': False,
        'has_modifiers': False,
        'has_status_management': False,
        'name': 'Emprendedor'
    },
    'crecimiento': {
        'max_products': 100,
        'has_qr': True,
        'has_modifiers': False,
        'has_status_management': True,
        'name': 'Crecimiento'
    },
    'elite': {
        'max_products': float('inf'),
        'has_qr': True,
        'has_modifiers': True,
        'has_status_management': True,
        'name': 'Élite'
    }
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
    
    # CRÍTICO: Asegurar que la fecha sea UTC-aware
    expires_at = restaurant.subscription_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    
    
    if expires_at > now:
        return True
        
    # Caso 2: Periodo de gracia (si se solicita)
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
    
    # Verificar que la suscripción esté activa
    if not is_subscription_active(restaurant):
        return False, "Tu suscripción ha expirado. Renueva tu plan para continuar."
    
    limits = get_plan_limits(restaurant.plan_type)
    max_products = limits['max_products']
    
    # Si es infinito, siempre permitir
    if max_products == float('inf'):
        return True, "Productos ilimitados"

    # Contar SOLO productos activos, no todos
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
            'badge_text': 'No encontrado'
        }
    
    # 2. CUENTA SUSPENDIDA ADMINISTRATIVAMENTE
    if not restaurant.is_active:
        return {
            'is_active': False,
            'status': 'inactive',
            'message': 'Cuenta suspendida administrativamente',
            'can_crud': False,
            'badge_class': 'bg-red-100 text-red-600',
            'badge_text': 'Suspendida'
        }
    
    # 3. SIN SUSCRIPCIÓN (Nunca ha pagado)
    if not restaurant.subscription_expires_at:
        return {
            'is_active': False,
            'status': 'no_subscription',
            'message': 'No tienes una suscripción activa',
            'can_crud': False,
            'badge_class': 'bg-yellow-100 text-yellow-600',
            'badge_text': 'Sin suscripción'
        }
    
    expires_at = restaurant.subscription_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    
    # 6. CALCULAR DELTA TEMPORAL
    delta = expires_at - now
    total_seconds = delta.total_seconds()
    
    # Calcular días restantes (redondeo hacia arriba para UX positiva)
    # Ejemplo: Si quedan 0.5 días, mostrar "1 día restante"
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
        if days_remaining <= 7:
            return {
                'is_active': True,
                'status': 'expiring_soon',
                'days_remaining': days_remaining,
                'expires_at': expires_at,
                'formatted_expiration': formatted_expiration,
                'can_crud': True,
                'message': f'⚠️ Tu suscripción expira en {days_remaining} día{"s" if days_remaining != 1 else ""}. Renueva pronto.',
                'badge_class': 'bg-yellow-100 text-yellow-700',
                'badge_text': 'Por expirar'
            }
        
        # Subcaso: Activa normal
        return {
            'is_active': True,
            'status': 'active',
            'days_remaining': days_remaining,
            'expires_at': expires_at,
            'formatted_expiration': formatted_expiration,
            'can_crud': True,
            'message': f'✅ Suscripción activa. {days_remaining} día{"s" if days_remaining != 1 else ""} restante{"s" if days_remaining != 1 else ""}.',
            'badge_class': 'bg-green-100 text-green-700',
            'badge_text': 'Activa'
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
            'days_remaining': days_remaining,  # Será negativo
            'days_grace_remaining': days_grace_remaining,
            'expires_at': expires_at,
            'formatted_expiration': formatted_expiration,
            'can_crud': False,
            'message': f'⚠️ Suscripción vencida. Tienes {days_grace_remaining} día{"s" if days_grace_remaining != 1 else ""} de gracia para renovar.',
            'badge_class': 'bg-orange-100 text-orange-700',
            'badge_text': 'Periodo de gracia'
        }
    
    # CASO C: EXPIRADA DEFINITIVAMENTE
    days_since_expiration = abs(days_remaining)
    
    return {
        'is_active': False,
        'status': 'expired',
        'days_remaining': days_remaining,  # Negativo
        'days_since_expiration': days_since_expiration,
        'expires_at': expires_at,
        'formatted_expiration': formatted_expiration,
        'can_crud': False,
        'message': f'Suscripción expirada hace {days_since_expiration} día{"s" if days_since_expiration != 1 else ""}. Renueva para continuar.',
        'badge_class': 'bg-red-100 text-red-700',
        'badge_text': 'Expirada'
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
    Útil después de un downgrade o cambio de plan.
    """
    if not restaurant:
        return

    limits = get_plan_limits(restaurant.plan_type)
    
    # --- 1. SANEAMIENTO DE PRODUCTOS ---
    max_products = limits['max_products']
    
    if max_products != float('inf'):
        # Obtener todos los productos activos ordenados por creación (o ID) ascendente
        # Queremos mantener los más viejos y desactivar los nuevos excedentes
        active_products = Product.query.filter_by(
            restaurant_id=restaurant.id, 
            is_active=True
        ).order_by(Product.id.asc()).all()
        
        current_count = len(active_products)
        
        if current_count > max_products:
            # Calcular cuántos sobran
            excess_count = current_count - max_products
            
            # Seleccionar los últimos 'excess_count' productos para desactivar
            products_to_deactivate = active_products[-excess_count:]
            
            for prod in products_to_deactivate:
                prod.is_active = False
            
            print(f"SANEAMIENTO: Desactivados {len(products_to_deactivate)} productos por límite de plan.")

    # --- 2. SANEAMIENTO DE ESTADO DE TIENDA ---
    if not limits.get('has_status_management', False):
        # Si el plan no permite gestionar estado, la tienda debe estar siempre ABIERTA por defecto
        if not restaurant.is_open:
            restaurant.is_open = True
            print("SANEAMIENTO: Restaurante forzado a ABIERTO por restricción de plan.")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"ERROR en sanitize_restaurant_limits: {e}")
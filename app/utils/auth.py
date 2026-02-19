from functools import wraps
from flask import session, redirect, url_for, flash, g, request, jsonify
import logging
from datetime import datetime
from app import db
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import is_subscription_active, check_feature_access

logger = logging.getLogger(__name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Por favor, inicia sesión para acceder a esta página.'}), 401
            flash('Por favor, inicia sesión para acceder a esta página.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def active_required(f):
    """
    Decorador que verifica:
    1. El usuario tiene un restaurante asociado
    2. El restaurante está activo (no suspendido)
    3. La suscripción no ha expirado
    
    Si alguna verificación falla, redirige apropiadamente.
    Para peticiones AJAX, retorna JSON.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Obtener restaurante actual
        restaurant = get_current_restaurant()
        
        # Helper para retornar error apropiado
        def return_error(message, code=401):
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': message}), code
            session.clear()
            flash(message, 'danger')
            return redirect(url_for('auth.login'))
        
        # Verificación 1: ¿Existe el restaurante?
        if not restaurant:
            logger.warning(
                f"Acceso sin restaurante - User: {session.get('user_id', 'unknown')} - "
                f"Ruta: {f.__name__}"
            )
            return return_error('Tu cuenta no está asociada a ningún restaurante o ha sido eliminada.')
        
        # Verificación 2: ¿Está activo el restaurante? (no suspendido)
        if not restaurant.is_active:
            logger.warning(
                f"Acceso a cuenta suspendida - Restaurant ID: {restaurant.id} - "
                f"Ruta: {f.__name__}"
            )
            return return_error('Tu cuenta ha sido suspendida. Contacta a soporte para más información.')
        
        # Verificación 3: ¿Está activa la suscripción (o en gracia)?
        if not is_subscription_active(restaurant, include_grace_period=True):
            logger.info(
                f"Acceso denegado (expirado total) - Restaurant ID: {restaurant.id} - "
                f"Expira: {restaurant.subscription_expires_at} - Ruta: {f.__name__}"
            )
            return return_error('Tu periodo de gracia ha terminado. Por favor selecciona o renueva tu plan para recuperar el acceso.')
        
        # Todo OK - permitir acceso
        return f(*args, **kwargs)
    
    return decorated_function

def feature_required(feature_name):
    """
    Decorador para verificar acceso a características específicas del plan.
    Debe usarse después de @login_required y @active_required.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            restaurant = get_current_restaurant()
            
            if not restaurant:
                return jsonify({'error': 'Restaurante no encontrado'}), 404
                
            if not check_feature_access(restaurant, feature_name):
                # Si es una petición AJAX/API
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'error': 'Plan insuficiente',
                        'message': f'Tu plan actual no incluye la función: {feature_name}'
                    }), 403
                
                # Para peticiones normales de navegación
                flash(f'Actualiza tu plan para acceder a esta función.', 'warning')
                return redirect(url_for('dashboard.subscription'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
    
from functools import wraps
from flask import session, redirect, url_for, flash, g, request, jsonify
import logging
from datetime import datetime
from app import db
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import is_subscription_active

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
    
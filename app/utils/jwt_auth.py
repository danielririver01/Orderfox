from functools import wraps
from flask import g, request, jsonify, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models import User, Restaurant
from app.utils.subscription import is_subscription_active, check_feature_access
import logging

logger = logging.getLogger(__name__)


def get_current_user_jwt():
    user_id = get_jwt_identity()
    if user_id:
        return User.query.get(user_id)
    return None


def get_current_restaurant_jwt():
    user = get_current_user_jwt()
    if user and user.restaurant:
        return user.restaurant
    return None


def jwt_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            logger.warning(f"JWT verification failed: {e}")
            return jsonify({
                'success': False,
                'error': 'unauthorized',
                'message': 'Token inválido o expirado. Por favor inicia sesión nuevamente.'
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def jwt_active_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.endpoint and 'subscription' in request.endpoint:
            return f(*args, **kwargs)

        restaurant = get_current_restaurant_jwt()

        def return_error(message, code=401):
            return jsonify({'success': False, 'error': message}), code

        if not restaurant:
            return return_error('Tu cuenta no está asociada a ningún restaurante.')

        if not restaurant.is_active:
            return return_error('Tu cuenta ha sido suspendida. Contacta a soporte para más información.')

        has_tokens = False
        if restaurant.users:
            owner = restaurant.users[0]
            if owner.token_wallet and owner.token_wallet.can_scan():
                has_tokens = True

        if not is_subscription_active(restaurant, include_grace_period=True) and not has_tokens:
            return return_error('Tu periodo de gracia ha terminado. Por favor renueva tu plan para recuperar el acceso.')

        g.is_expired = not is_subscription_active(restaurant, include_grace_period=False)
        g.has_tokens = has_tokens

        return f(*args, **kwargs)
    return decorated_function


def jwt_feature_required(feature_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            restaurant = get_current_restaurant_jwt()
            if not restaurant:
                return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
            if not check_feature_access(restaurant, feature_name):
                return jsonify({
                    'success': False,
                    'error': 'Plan insuficiente',
                    'message': f'Tu plan actual no incluye la función: {feature_name}'
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

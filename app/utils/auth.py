from functools import wraps
from flask import session, redirect, url_for, flash, g, request, jsonify
import logging
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import is_subscription_active, check_feature_access

logger = logging.getLogger(__name__)


# ── Decoradores Unificados ─────────────────────────────────────────

def require_auth(f):
    """
    Decorador unificado que detecta automáticamente JWT o sesión Flask.
    Reemplaza a @login_required y @jwt_login_required.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        is_bearer = auth_header.startswith('Bearer ')

        if is_bearer:
            from flask_jwt_extended import verify_jwt_in_request
            try:
                verify_jwt_in_request()
                return f(*args, **kwargs)
            except Exception as e:
                logger.warning(f"JWT verification failed in require_auth: {e}")
                return jsonify({
                    'success': False,
                    'error': 'unauthorized',
                    'message': 'Token inválido o expirado. Por favor inicia sesión nuevamente.'
                }), 401
        elif 'user_id' in session or 'employee_id' in session:
            # user_id = dueño; employee_id = empleado (portal PIN).
            return f(*args, **kwargs)
        else:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': 'unauthorized',
                    'message': 'Por favor, inicia sesión para acceder.'
                }), 401
            flash('Por favor, inicia sesión para acceder a esta página.', 'warning')
            return redirect(url_for('auth.login'))
    return decorated_function


def _get_restaurant_unified():
    """Get the restaurant using JWT or session (auto-detect)."""
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    from app.models import Restaurant as RestModel

    auth_header = request.headers.get('Authorization', '')
    is_bearer = auth_header.startswith('Bearer ')

    if is_bearer:
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            from app.models import User
            user = User.query.get(user_id)
            if user and user.restaurant:
                return user.restaurant
        except Exception:
            pass
        return None

    if 'user_id' in session or 'employee_id' in session:
        return get_current_restaurant()
    return None


def require_active(f):
    """
    Decorador unificado que verifica cuenta activa (JWT o sesión).
    Reemplaza a @active_required y @jwt_active_required.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.endpoint and 'subscription' in request.endpoint:
            return f(*args, **kwargs)

        restaurant = _get_restaurant_unified()

        def return_error(message, code=401, redirect_to='auth.login'):
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': message}), code
            flash(message, 'warning')
            return redirect(url_for(redirect_to))

        if not restaurant:
            return return_error('Tu cuenta no está asociada a ningún restaurante.', redirect_to='auth.setup_account')

        if not restaurant.is_active:
            return return_error('Tu cuenta ha sido suspendida. Contacta a soporte para más información.')

        has_tokens = False
        # v2.1.0: el dueño se identifica por role, nunca por orden en la lista
        # (users[0]). El primer usuario puede ser un empleado.
        owner = next((u for u in restaurant.users if u.role == 'owner'), None)
        if owner and owner.token_wallet and owner.token_wallet.can_scan():
            has_tokens = True

        if not is_subscription_active(restaurant, include_grace_period=True) and not has_tokens:
            return return_error('Tu periodo de gracia ha terminado. Por favor renueva tu plan para recuperar el acceso.', redirect_to='dashboard.subscription')

        g.is_expired = not is_subscription_active(restaurant, include_grace_period=False)
        g.has_tokens = has_tokens

        return f(*args, **kwargs)
    return decorated_function


def require_feature(feature_name):
    """
    Decorador unificado para verificar acceso a características.
    Reemplaza a @feature_required y @jwt_feature_required.
    Debe usarse después de @require_auth y @require_active.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            restaurant = _get_restaurant_unified()

            if not restaurant:
                return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

            if not check_feature_access(restaurant, feature_name):
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'error': 'Plan insuficiente',
                        'message': f'Tu plan actual no incluye la función: {feature_name}'
                    }), 403
                flash(f'Actualiza tu plan para acceder a esta función.', 'warning')
                return redirect(url_for('dashboard.subscription'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_role_check(*roles):
    """
    Chequeo de rol reutilizable (v2.1.0). Verifica que el usuario autenticado
    tiene uno de los roles permitidos y está activo.

    Roles válidos: owner | cashier | waiter.

    Retorna None si pasa; si no, retorna una respuesta:
    - Web (sesión Flask): flash + redirect a /empleado/<slug> (portal del
      empleado) o /login si es dueño.
    - API móvil (Bearer JWT) / JSON: 403 JSON.

    Sirve tanto para el decorador @require_role como para
    blueprint.before_request.
    """
    from app.models import User

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        user = None
        try:
            verify_jwt_in_request()
            user = User.query.get(get_jwt_identity())
        except Exception:
            user = None
        if not user or user.role not in roles or not user.is_active:
            return jsonify({
                'success': False,
                'error': 'forbidden',
                'message': 'No tienes permisos para realizar esta acción.',
            }), 403
        return None

    # v2.1.2: la sesión del empleado vive en 'employee_id' (no 'user_id').
    # Si ambas claves coexisten (estado residual del mismo navegador), el
    # dueño (user_id) tiene prioridad. Normalmente nunca coexisten: cada
    # login explícito limpia la clave del otro rol (última acción gana).
    user_id = session.get('user_id')
    employee_id = session.get('employee_id')
    user = None
    if user_id:
        user = User.query.get(user_id)
    elif employee_id:
        user = User.query.get(employee_id)
    if not user or user.role not in roles or not user.is_active:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'forbidden',
                'message': 'No tienes permisos para realizar esta acción.',
            }), 403
        if user and user.role == 'owner':
            flash('Tu sesión no tiene permisos para esta sección.', 'warning')
            return redirect(url_for('auth.login'))
        if user and user.restaurant:
            flash('No tienes permisos para esta sección.', 'error')
            return redirect(url_for('employee_portal.login', slug=user.restaurant.slug))
        flash('Debes iniciar sesión para acceder.', 'warning')
        return redirect(url_for('auth.login'))
    return None


def require_role(*roles):
    """
    Decorador de roles (v2.1.0). Verifica que el usuario autenticado tiene uno
    de los roles permitidos y está activo. Debe usarse después de
    @require_auth y @require_active.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = require_role_check(*roles)
            if response is not None:
                return response
            return f(*args, **kwargs)
        return decorated_function
    return decorator
    
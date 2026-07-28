from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, create_refresh_token
from app.utils.auth import require_auth, require_active
from app.utils.jwt_auth import get_current_user_jwt, get_current_restaurant_jwt
from app.services.auth_service import AuthService
from app.services.subscription_service import SubscriptionService
from app.services.token_service import TokenService
from app.models import User
import mercadopago

api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')


@api_auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email y contraseña son requeridos'}), 400

    result, error = AuthService.api_login(email, password)
    if error:
        status_code = 403 if error.get('error_code') == 'pending_payment' else 401
        response = {'success': False, 'error': error.get('error_code', 'INVALID_CREDENTIALS')}
        if error.get('message'):
            response['message'] = error['message']
        if error.get('redirect'):
            response['redirect'] = error['redirect']
        return jsonify(response), status_code

    return jsonify({
        'success': True,
        'data': result
    }), 200


@api_auth_bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({
        'success': True,
        'message': 'Sesión cerrada. Elimina el token de tu dispositivo.'
    }), 200


@api_auth_bp.route('/plans', methods=['GET'])
def get_plans():
    plans_config = SubscriptionService.get_plans_config()

    return jsonify({
        'success': True,
        'data': plans_config
    }), 200


@api_auth_bp.route('/payment/initiate', methods=['POST'])
@require_auth
@require_active
def initiate_payment():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    plan_type = data.get('plan_type', 'crendedor')
    if plan_type not in ['emprendedor', 'crecimiento', 'elite']:
        return jsonify({'success': False, 'error': 'Plan inválido'}), 400

    user = get_current_user_jwt()
    restaurant = get_current_restaurant_jwt()

    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    base_url = current_app.config.get('BASE_URL', 'https://velzia.co')
    preference_data, plan_info, coupon = SubscriptionService.build_mp_preference_data(
        plan_type, restaurant.id, base_url
    )

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        checkout_url = preference.get("init_point", "#")
        preference_id = preference.get('id')
        if preference_id and coupon:
            SubscriptionService.reserve_coupon(coupon, preference_id)
    except Exception as e:
        current_app.logger.error(f"Error creating MP preference: {e}")
        return jsonify({'success': False, 'error': 'Error al conectar con la pasarela de pago'}), 500

    return jsonify({
        'success': True,
        'data': {
            'checkout_url': checkout_url,
            'preference_id': preference_id,
            'plan': {
                'name': plan_info['name'],
                'price': plan_info['price_raw']
            }
        }
    }), 200


@api_auth_bp.route('/mobile-sync', methods=['POST'])
def mobile_sync():
    data = request.get_json()
    if not data or not data.get('clerk_token'):
        return jsonify({'success': False, 'error': 'clerk_token requerido'}), 400

    clerk_token = data.get('clerk_token')
    clerk_id = TokenService.verify_clerk_jwt(clerk_token)
    if not clerk_id:
        return jsonify({'success': False, 'error': 'Token de Clerk inválido o expirado'}), 401

    user = User.query.filter_by(clerk_id=clerk_id).first()
    if not user:
        return jsonify({'success': False, 'error': 'Usuario no encontrado. Completa el registro en la web primero.'}), 404

    iss = current_app.config.get('BASE_URL', 'https://velzia.co')
    access_token = create_access_token(identity=str(user.id), additional_claims={'iss': iss})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={'iss': iss})

    return jsonify({
        'success': True,
        'data': {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'restaurant_id': user.restaurant_id,
            }
        }
    }), 200


@api_auth_bp.route('/refresh', methods=['POST'])
def refresh():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Refresh token requerido'}), 400

    refresh_token = data.get('refresh_token')

    result, error = AuthService.api_refresh_token(refresh_token)
    if error:
        status = 404 if error.get('error_code') == 'USER_NOT_FOUND' else 401
        return jsonify({'success': False, 'error': error['message']}), status

    return jsonify({
        'success': True,
        'data': result
    }), 200

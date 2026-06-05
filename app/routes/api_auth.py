from flask import Blueprint, request, jsonify, current_app
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, get_current_user_jwt, get_current_restaurant_jwt
from app.services.auth_service import AuthService
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


@api_auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    email = data.get('email', '').strip().lower()
    plan_type = data.get('plan_type', 'emprendedor')

    result, error = AuthService.api_register(email, plan_type)
    if error:
        status = 409 if error.get('error_code') == 'ACCOUNT_EXISTS' else 400
        return jsonify({'success': False, 'error': error['message']}), status

    return jsonify({
        'success': True,
        'data': result
    }), 200


@api_auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    temp_token = data.get('temp_token')
    otp_code = data.get('otp_code')

    result, error = AuthService.verify_otp(temp_token, otp_code)
    if error:
        return jsonify({'success': False, 'error': error['message']}), 400

    return jsonify({
        'success': True,
        'data': result
    }), 200


@api_auth_bp.route('/setup-account', methods=['POST'])
def setup_account():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    verified_token = data.get('verified_token')

    result, error = AuthService.api_setup_account(verified_token, data)
    if error:
        return jsonify({'success': False, 'error': error['message']}), 400

    return jsonify({
        'success': True,
        'data': result
    }), 201


@api_auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Email es requerido'}), 400

    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'success': False, 'error': 'Email es requerido'}), 400

    token, user_email = AuthService.create_password_reset_token(email)
    if token and user_email:
        base_url = current_app.config.get('BASE_URL', 'https://velzia.co')
        reset_url = f"{base_url}/reset-password/{token}"
        AuthService.send_password_reset_email(user_email, reset_url)

    return jsonify({
        'success': True,
        'message': 'Si el correo está registrado, recibirás un enlace de recuperación.'
    }), 200


@api_auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({'success': False, 'error': 'Token y nueva contraseña son requeridos'}), 400

    pwd_error = AuthService.validate_password(new_password)
    if pwd_error:
        return jsonify({'success': False, 'error': pwd_error}), 400

    email, verify_error = AuthService.verify_reset_token(token)
    if verify_error:
        return jsonify({'success': False, 'error': verify_error['message']}), 400

    user, update_error = AuthService.set_new_password(email, new_password)
    if update_error:
        return jsonify({'success': False, 'error': update_error['message']}), 404

    return jsonify({
        'success': True,
        'message': 'Contraseña actualizada exitosamente.'
    }), 200


@api_auth_bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({
        'success': True,
        'message': 'Sesión cerrada. Elimina el token de tu dispositivo.'
    }), 200


@api_auth_bp.route('/plans', methods=['GET'])
def get_plans():
    plans_config = AuthService.get_plans_config()

    return jsonify({
        'success': True,
        'data': plans_config
    }), 200


@api_auth_bp.route('/payment/initiate', methods=['POST'])
@jwt_login_required
@jwt_active_required
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
    preference_data, plan_info = AuthService.build_mp_preference_data(
        plan_type, restaurant.id, base_url
    )

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        checkout_url = preference.get("init_point", "#")
        preference_id = preference.get('id')
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

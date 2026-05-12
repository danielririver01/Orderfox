from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, create_refresh_token
from datetime import datetime, timedelta, timezone
from flask_mail import Message
from app import db
from app.models import User, Restaurant, TrialHistory
from app.utils.jwt_auth import jwt_login_required, jwt_active_required
from app.utils.subscription import get_plan_limits, AI_TOKEN_LIMITS, sanitize_restaurant_limits, initialize_or_reset_token_wallet
from app.utils.image_handler import allowed_file
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import random
import re
import unicodedata
import mercadopago

api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')


RESERVED_SLUGS = {
    'scanner-ia', 'admin', 'api', 'dashboard', 'velzia', 'soporte', 'help',
    'billing', 'account', 'login', 'register', 'auth', 'public', 'menu',
    'order', 'status', 'health', 'test', 'scanner', 'ia', 'ai', 'bot'
}


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, otp):
    try:
        from app import mail
        from flask import render_template
        msg = Message('Código de Verificación - Velzia', recipients=[email])
        msg.html = render_template('email/otp.html', otp=otp)
        msg.body = f'Tu código de verificación para Velzia es: {otp}'
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending OTP email: {e}")
        return False


@api_auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email y contraseña son requeridos'}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({'success': False, 'error': 'Credenciales inválidas'}), 401

    if user.restaurant and not user.restaurant.is_active:
        return jsonify({
            'success': False,
            'error': 'pending_payment',
            'message': 'Tu suscripción está pendiente de pago.',
            'redirect': '/payment'
        }), 403

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    restaurant_data = None
    if user.restaurant:
        r = user.restaurant
        restaurant_data = {
            'id': r.id,
            'name': r.name,
            'slug': r.slug,
            'plan_type': r.plan_type,
            'is_open': r.is_open,
            'is_active': r.is_active
        }

    return jsonify({
        'success': True,
        'data': {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'restaurant_id': user.restaurant_id
            },
            'restaurant': restaurant_data
        }
    }), 200


@api_auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    email = data.get('email', '').strip().lower()
    plan_type = data.get('plan_type', 'emprendedor')

    if not email:
        return jsonify({'success': False, 'error': 'Email es requerido'}), 400

    if plan_type not in ['trial', 'emprendedor', 'crecimiento', 'elite']:
        return jsonify({'success': False, 'error': 'Plan inválido'}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.restaurant:
        return jsonify({
            'success': False,
            'error': 'Este email ya tiene una cuenta activa. Por favor inicia sesión.'
        }), 409

    if existing_user:
        access_token = create_access_token(identity=existing_user.id)
        otp = generate_otp()
        existing_otp_data = {
            'otp': otp,
            'email': email,
            'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            'plan_type': plan_type
        }
        access_token_obj = create_access_token(
            identity=existing_user.id,
            additional_claims={'type': 'register_verify', 'otp_data': existing_otp_data}
        )
        send_otp_email(email, otp)
        return jsonify({
            'success': True,
            'data': {
                'message': 'Se ha enviado un código de verificación a tu email',
                'temp_token': access_token_obj,
                'existing_user': True
            }
        }), 200

    otp = generate_otp()
    temp_token_data = {
        'email': email,
        'plan_type': plan_type,
        'otp': otp,
        'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    }

    temp_token = create_access_token(
        identity='register_temp',
        additional_claims={'type': 'register_temp', 'data': temp_token_data},
        expires_delta=timedelta(minutes=10)
    )

    send_otp_email(email, otp)

    return jsonify({
        'success': True,
        'data': {
            'message': 'Se ha enviado un código de verificación a tu email',
            'temp_token': temp_token
        }
    }), 200


@api_auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    temp_token = data.get('temp_token')
    otp_code = data.get('otp_code')

    if not temp_token or not otp_code:
        return jsonify({'success': False, 'error': 'Token y código OTP son requeridos'}), 400

    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(temp_token)
        token_type = decoded.get('sub') == 'register_temp' and decoded.get('type')

        if token_type == 'register_temp':
            token_data = decoded.get('data', {})
        elif token_type == 'register_verify':
            token_data = decoded.get('otp_data', {})
        else:
            return jsonify({'success': False, 'error': 'Token inválido'}), 400

        expires_at = datetime.fromisoformat(token_data.get('expires_at'))
        if datetime.now(timezone.utc) > expires_at:
            return jsonify({'success': False, 'error': 'El código ha expirado'}), 400

        if token_data.get('otp') != otp_code:
            return jsonify({'success': False, 'error': 'Código incorrecto'}), 400

        email = token_data.get('email')
        plan_type = token_data.get('plan_type')

        verify_token = create_access_token(
            identity='register_verified',
            additional_claims={
                'type': 'register_verified',
                'data': {'email': email, 'plan_type': plan_type}
            },
            expires_delta=timedelta(minutes=30)
        )

        return jsonify({
            'success': True,
            'data': {
                'message': 'Código verificado exitosamente',
                'verified_token': verify_token
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"OTP verification error: {e}")
        return jsonify({'success': False, 'error': 'Token inválido o expirado'}), 400


@api_auth_bp.route('/setup-account', methods=['POST'])
def setup_account():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    verified_token = data.get('verified_token')
    if not verified_token:
        return jsonify({'success': False, 'error': 'Token de verificación requerido'}), 400

    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(verified_token)
        if decoded.get('type') != 'register_verified':
            return jsonify({'success': False, 'error': 'Token inválido'}), 400

        token_data = decoded.get('data', {})
        email = token_data.get('email')
        plan_type = token_data.get('plan_type')
    except Exception:
        return jsonify({'success': False, 'error': 'Token inválido o expirado'}), 400

    restaurant_name = data.get('restaurant_name', '').strip()
    whatsapp_phone = data.get('whatsapp_phone', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not restaurant_name or not whatsapp_phone or not username or not password:
        return jsonify({'success': False, 'error': 'Todos los campos son requeridos'}), 400

    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        return jsonify({
            'success': False,
            'error': 'La contraseña debe tener al menos 8 caracteres, una mayúscula y un número'
        }), 400

    slug = unicodedata.normalize('NFKD', restaurant_name).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^\w\s-]', '', slug).strip().lower()
    slug = re.sub(r'[-\s]+', '-', slug)

    if slug in RESERVED_SLUGS:
        return jsonify({
            'success': False,
            'error': f'El nombre "{restaurant_name}" está reservado. Elige otro nombre.'
        }), 400

    base_slug = slug
    counter = 1
    while Restaurant.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    is_trial = plan_type == 'trial'

    if is_trial:
        past_trial = Restaurant.query.filter_by(whatsapp_phone=whatsapp_phone, has_used_trial=True).first()
        past_history = TrialHistory.query.filter(
            db.or_(TrialHistory.email == email, TrialHistory.whatsapp_phone == whatsapp_phone)
        ).first()
        if past_trial or past_history:
            return jsonify({
                'success': False,
                'error': 'Este correo o número ya disfrutó de una prueba gratuita. Elige un plan pago.'
            }), 400

        trial_expires = datetime.now(timezone.utc) + timedelta(days=10)
        restaurant = Restaurant(
            name=restaurant_name,
            slug=slug,
            whatsapp_phone=whatsapp_phone,
            plan_type='trial',
            is_active=True,
            subscription_expires_at=trial_expires,
            is_open=True,
            has_used_trial=False
        )
    else:
        restaurant = Restaurant(
            name=restaurant_name,
            slug=slug,
            whatsapp_phone=whatsapp_phone,
            plan_type=plan_type,
            is_active=False,
            subscription_expires_at=None,
            is_open=True,
            has_used_trial=False
        )

    db.session.add(restaurant)
    db.session.flush()

    user = User(
        email=email,
        username=username,
        restaurant_id=restaurant.id
    )
    user.set_password(password)
    db.session.add(user)

    if is_trial:
        db.session.add(TrialHistory(email=email, whatsapp_phone=whatsapp_phone))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Setup account error: {e}")
        return jsonify({'success': False, 'error': 'Error al crear la cuenta. Inténtalo de nuevo.'}), 500

    if is_trial:
        initialize_or_reset_token_wallet(user)

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        'success': True,
        'data': {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            },
            'restaurant': {
                'id': restaurant.id,
                'name': restaurant.name,
                'slug': restaurant.slug,
                'plan_type': restaurant.plan_type
            }
        }
    }), 201


@api_auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Email es requerido'}), 400

    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'success': False, 'error': 'Email es requerido'}), 400

    user = User.query.filter_by(email=email).first()
    if user:
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = s.dumps(user.email, salt='recover-key')
        base_url = current_app.config.get('BASE_URL', 'https://velzia.co')
        reset_url = f"{base_url}/reset-password/{token}"

        try:
            from app import mail
            from flask import render_template
            msg = Message('Restablecer Contraseña - Velzia', recipients=[user.email])
            msg.html = render_template('email/reset_password.html', reset_url=reset_url)
            msg.body = f'Para restablecer tu contraseña, visita: {reset_url}'
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Error sending reset email: {e}")

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

    if len(new_password) < 8 or not any(c.isupper() for c in new_password) or not any(c.isdigit() for c in new_password):
        return jsonify({
            'success': False,
            'error': 'La contraseña debe tener al menos 8 caracteres, una mayúscula y un número'
        }), 400

    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='recover-key', max_age=3600)
    except SignatureExpired:
        return jsonify({'success': False, 'error': 'El enlace ha expirado. Solicita uno nuevo.'}), 400
    except BadSignature:
        return jsonify({'success': False, 'error': 'El enlace no es válido.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'error': 'Usuario no encontrado.'}), 404

    user.set_password(new_password)
    db.session.commit()

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
    plans_config = {
        'trial': {
            'type': 'trial',
            'name': 'Prueba Gratuita Premium',
            'price_cop': 0,
            'duration_days': 10,
            'features': {
                'max_products': 'ilimitado',
                'has_qr': True,
                'has_table_qr': True,
                'has_modifiers': True,
                'has_status_management': True,
                'ai_tokens': AI_TOKEN_LIMITS.get('trial', 10)
            }
        },
        'emprendedor': {
            'type': 'emprendedor',
            'name': 'Emprendedor',
            'price_cop': 30000,
            'duration_days': 30,
            'features': {
                'max_products': 25,
                'has_qr': True,
                'has_table_qr': False,
                'has_modifiers': False,
                'has_status_management': False,
                'ai_tokens': AI_TOKEN_LIMITS.get('emprendedor', 150)
            }
        },
        'crecimiento': {
            'type': 'crecimiento',
            'name': 'Crecimiento',
            'price_cop': 40000,
            'duration_days': 30,
            'features': {
                'max_products': 100,
                'has_qr': True,
                'has_table_qr': True,
                'has_modifiers': False,
                'has_status_management': True,
                'ai_tokens': AI_TOKEN_LIMITS.get('crecimiento', 500)
            }
        },
        'elite': {
            'type': 'elite',
            'name': 'Élite',
            'price_cop': 50000,
            'duration_days': 30,
            'features': {
                'max_products': 'ilimitado',
                'has_qr': True,
                'has_table_qr': True,
                'has_modifiers': True,
                'has_status_management': True,
                'ai_tokens': AI_TOKEN_LIMITS.get('elite', 3000)
            }
        }
    }

    top_up_packs = [
        {'id': '5k', 'label': 'Pack Básico', 'price_cop': 5000, 'tokens': 15, 'badge': 'Starter'},
        {'id': '10k', 'label': 'Pack Pro', 'price_cop': 10000, 'tokens': 35, 'badge': 'Popular'}
    ]

    return jsonify({
        'success': True,
        'data': {
            'plans': list(plans_config.values()),
            'top_up_packs': top_up_packs
        }
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

    from app.utils.jwt_auth import get_current_user_jwt, get_current_restaurant_jwt
    user = get_current_user_jwt()
    restaurant = get_current_restaurant_jwt()

    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    plans_data = {
        'emprendedor': {'name': 'Plan Emprendedor', 'price': 30000},
        'crecimiento': {'name': 'Plan Crecimiento', 'price': 40000},
        'elite': {'name': 'Plan Élite', 'price': 50000}
    }

    plan_info = plans_data[plan_type]

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))

    base_url = current_app.config.get('BASE_URL', 'https://velzia.co')

    preference_data = {
        "items": [
            {
                "title": f"Suscripción Velzia - {plan_info['name']}",
                "quantity": 1,
                "unit_price": float(plan_info['price']),
                "currency_id": "COP"
            }
        ],
        "back_urls": {
            "success": f"{base_url}/payment-callback",
            "failure": f"{base_url}/payment",
            "pending": f"{base_url}/payment-callback"
        },
        "auto_return": "approved",
        "external_reference": f"{restaurant.id}:{plan_type}",
        "notification_url": f"{base_url}/webhook",
        "payment_methods": {
            "excluded_payment_types": [{"id": "ticket"}],
            "installments": 1
        }
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        checkout_url = preference.get("init_point", "#")
    except Exception as e:
        current_app.logger.error(f"Error creating MP preference: {e}")
        return jsonify({'success': False, 'error': 'Error al conectar con la pasarela de pago'}), 500

    return jsonify({
        'success': True,
        'data': {
            'checkout_url': checkout_url,
            'preference_id': preference.get('id'),
            'plan': plan_info
        }
    }), 200


@api_auth_bp.route('/refresh', methods=['POST'])
def refresh():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Refresh token requerido'}), 400

    refresh_token = data.get('refresh_token')
    if not refresh_token:
        return jsonify({'success': False, 'error': 'Refresh token requerido'}), 400

    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(refresh_token)
        user_id = decoded.get('sub')

        if not user_id:
            return jsonify({'success': False, 'error': 'Token inválido'}), 401

        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404

        new_access_token = create_access_token(identity=str(user.id))

        restaurant_data = None
        if user.restaurant:
            r = user.restaurant
            restaurant_data = {
                'id': r.id,
                'name': r.name,
                'slug': r.slug,
                'plan_type': r.plan_type,
                'is_open': r.is_open,
                'is_active': r.is_active
            }

        return jsonify({
            'success': True,
            'data': {
                'access_token': new_access_token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                },
                'restaurant': restaurant_data
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Token refresh error: {e}")
        return jsonify({'success': False, 'error': 'Token inválido o expirado'}), 401

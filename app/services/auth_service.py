"""
AuthService — Business logic for authentication and account operations.
Shared by web routes (auth_bp) and API routes (api_auth_bp).

Pattern: @staticmethod methods returning (result, None) / (None, error_dict).
"""
from datetime import datetime, timedelta, timezone
import random
import re
import unicodedata
from flask import current_app, render_template
from flask_mail import Message
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app.models import db, User, Restaurant, TrialHistory, AITokenWallet, PreRegistration
from app.extensions import mail
from app.utils.subscription import (
    sanitize_restaurant_limits,
    initialize_or_reset_token_wallet,
    get_plan_limits,
    AI_TOKEN_LIMITS,
    TOP_UP_PACKS,
)
from app.utils.constants import RESERVED_SLUGS
import mercadopago
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token


class AuthService:
    """Business logic for authentication and account operations."""

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def generate_otp():
        """Generate a random 6-digit OTP code."""
        return str(random.randint(100000, 999999))

    @staticmethod
    def generate_slug(name):
        """Convert a restaurant name to a URL-safe slug (ASCII, lowercase, hyphenated)."""
        slug = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
        slug = re.sub(r'[^\w\s-]', '', slug).strip().lower()
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug

    @staticmethod
    def ensure_unique_slug(base_slug):
        """Append -N suffix until slug is unique in the restaurants table."""
        slug = base_slug
        counter = 1
        while Restaurant.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    @staticmethod
    def is_reserved_slug(slug):
        """Return True if slug is a reserved system name."""
        return slug in RESERVED_SLUGS

    @staticmethod
    def validate_password(password):
        """
        Check password complexity.
        Returns error message string or None if valid.
        """
        if len(password) < 8:
            return 'La contraseña debe tener al menos 8 caracteres, una mayúscula y un número.'
        if not any(c.isupper() for c in password):
            return 'La contraseña debe tener al menos 8 caracteres, una mayúscula y un número.'
        if not any(c.isdigit() for c in password):
            return 'La contraseña debe tener al menos 8 caracteres, una mayúscula y un número.'
        return None

    # ── Email ───────────────────────────────────────────────

    @staticmethod
    def send_otp_email(email, otp):
        """Send OTP verification email. Returns True on success."""
        try:
            msg = Message('Código de Verificación - Velzia', recipients=[email])
            msg.html = render_template('email/otp.html', otp=otp)
            msg.body = f'Tu código de verificación para Velzia es: {otp}'
            mail.send(msg)
            return True
        except Exception as e:
            current_app.logger.error(f"Error sending OTP email: {e}")
            return False

    @staticmethod
    def send_password_reset_email(user_email, reset_url):
        """Send password reset email. Returns True on success."""
        try:
            msg = Message('Restablecer Contraseña - Velzia', recipients=[user_email])
            msg.html = render_template('email/reset_password.html', reset_url=reset_url)
            msg.body = f'Para restablecer tu contraseña, visita: {reset_url}'
            mail.send(msg)
            return True
        except Exception as e:
            current_app.logger.error(f"Error sending password reset email: {e}")
            return False

    # ── Clerk Sync ──────────────────────────────────────────

    @staticmethod
    def sync_or_create_user(clerk_id, email, username=None):
        """
        Find existing user by email or create a new one with Clerk identity.

        Returns:
            (user, is_new, selected_plan_or_error)
            On success: (user_obj, True/False, plan_string_or_None)
            On failure: (None, False, error_dict)
        """
        if not email or not clerk_id:
            return None, False, {'error_code': 'MISSING_FIELDS',
                                 'message': 'Identification is required'}

        username = username or email.split('@')[0]
        user = User.query.filter_by(email=email).first()

        if not user:
            try:
                pre_reg = PreRegistration.query.filter_by(email=email).first()
                selected_plan = pre_reg.selected_plan if pre_reg else 'trial'

                user = User(
                    restaurant_id=None,
                    username=username,
                    email=email,
                    password=generate_password_hash(str(clerk_id)),
                    clerk_id=clerk_id,
                )
                db.session.add(user)
                db.session.flush()

                plan_tokens = AI_TOKEN_LIMITS.get(selected_plan, 0)
                token_wallet = AITokenWallet(
                    user_id=user.id,
                    plan_limit=plan_tokens if selected_plan == 'trial' else None,
                    plan_tokens=plan_tokens,
                    extra_tokens=0,
                )
                db.session.add(token_wallet)

                if pre_reg:
                    db.session.delete(pre_reg)

                db.session.commit()
                return user, True, selected_plan

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error creating Clerk user: {e}")
                return None, False, {'error_code': 'REGISTRATION_ERROR',
                                     'message': f'Error al crear usuario: {str(e)}'}

        # Link clerk_id if missing
        if not user.clerk_id:
            user.clerk_id = clerk_id
            db.session.commit()

        # Initialize token wallet if missing
        if not user.token_wallet:
            initialize_or_reset_token_wallet(user)

        return user, False, None

    # ── Traditional Auth ────────────────────────────────────

    @staticmethod
    def authenticate(email, password):
        """
        Authenticate user with email and password.
        Returns (user, None) or (None, error_dict).
        """
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return None, {'error_code': 'INVALID_CREDENTIALS',
                          'message': 'Email o contraseña incorrectos'}
        return user, None

    @staticmethod
    def create_password_reset_token(email):
        """
        Generate a timed password-reset token for the user.
        Returns (token, user_email) or (None, None) if user not found (silent).
        """
        user = User.query.filter_by(email=email).first()
        if not user:
            return None, None
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = s.dumps(user.email, salt='recover-key')
        return token, user.email

    @staticmethod
    def verify_reset_token(token):
        """
        Verify a password-reset token and extract the email.
        Returns (email, None) or (None, error_dict).
        """
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            email = s.loads(token, salt='recover-key', max_age=3600)
            return email, None
        except SignatureExpired:
            return None, {'error_code': 'TOKEN_EXPIRED',
                          'message': 'El enlace ha expirado. Por favor solicita uno nuevo.'}
        except BadSignature:
            return None, {'error_code': 'INVALID_TOKEN',
                          'message': 'El enlace no es válido.'}
        except Exception as e:
            current_app.logger.error(f"Error verifying reset token: {e}")
            return None, {'error_code': 'TOKEN_ERROR',
                          'message': 'Ocurrió un error inesperado.'}

    @staticmethod
    def set_new_password(email, password):
        """
        Set a new password for the given email.
        Returns (user, None) or (None, error_dict).
        """
        user = User.query.filter_by(email=email).first()
        if not user:
            return None, {'error_code': 'USER_NOT_FOUND',
                          'message': 'Usuario no encontrado.'}
        user.set_password(password)
        db.session.commit()
        return user, None

    # ── Plan Selection ──────────────────────────────────────

    @staticmethod
    def save_plan_selection(email, plan):
        """
        Save or update a pre-registration plan selection.
        Returns (pre_reg, None) or (None, error_dict).
        """
        valid_plans = ['trial', 'emprendedor', 'premium', 'elite']
        if plan not in valid_plans:
            return None, {'error_code': 'INVALID_PLAN',
                          'message': f'Plan inválido: {plan}'}

        try:
            pre_reg = PreRegistration.query.filter_by(email=email).first()
            if pre_reg:
                pre_reg.selected_plan = plan
                pre_reg.created_at = datetime.now(timezone.utc)
            else:
                pre_reg = PreRegistration(email=email, selected_plan=plan)
                db.session.add(pre_reg)
            db.session.commit()
            return pre_reg, None
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving plan selection: {e}")
            return None, {'error_code': 'SAVE_ERROR',
                          'message': f'Error al guardar: {str(e)}'}

    # ── Trial Eligibility ───────────────────────────────────

    @staticmethod
    def check_trial_eligibility(email, phone):
        """
        Check whether this email/phone has already used a trial.

        Returns:
            (blocked: bool, message: str or None)
            blocked=True means the trial is NOT allowed.
        """
        past_active_trial = Restaurant.query.filter_by(
            whatsapp_phone=phone, has_used_trial=True
        ).first()
        past_history_trial = TrialHistory.query.filter(
            db.or_(TrialHistory.email == email, TrialHistory.whatsapp_phone == phone)
        ).first()

        if past_active_trial or past_history_trial:
            return True, ('Este correo o número ya disfrutó de una prueba gratuita. '
                          'Por favor elige un plan pago para tu nueva sucursal.')
        return False, None

    # ── Account Setup (Web) ─────────────────────────────────

    @staticmethod
    def create_restaurant_from_setup(user, email, restaurant_name, phone,
                                     selected_plan, admin_name=None, password=None):
        """
        Create a restaurant, link the user, and handle trial history.

        Returns:
            (restaurant_obj, None) on success,
            (None, error_message_string) on failure.
        """
        slug = AuthService.generate_slug(restaurant_name)
        if AuthService.is_reserved_slug(slug):
            return None, (f'El nombre "{restaurant_name}" está reservado para el sistema. '
                          'Por favor elige uno más original para tu negocio.')

        slug = AuthService.ensure_unique_slug(slug)
        is_trial = (selected_plan == 'trial')

        if is_trial:
            trial_expires_at = datetime.now(timezone.utc) + timedelta(days=10)
            restaurant = Restaurant(
                name=restaurant_name,
                slug=slug,
                whatsapp_phone=phone,
                plan_type='trial',
                is_active=True,
                subscription_expires_at=trial_expires_at,
                is_open=True,
                has_used_trial=False,
            )
        else:
            restaurant = Restaurant(
                name=restaurant_name,
                slug=slug,
                whatsapp_phone=phone,
                plan_type=selected_plan,
                is_active=False,
                subscription_expires_at=None,
                is_open=True,
                has_used_trial=False,
            )

        db.session.add(restaurant)
        db.session.flush()

        # Link the user to this restaurant
        user.restaurant_id = restaurant.id

        # For non-Clerk users, update identity fields
        if not user.clerk_id:
            user.username = (admin_name or '').strip()
            if password:
                user.set_password(password)

        if is_trial:
            trial_record = TrialHistory(email=email, whatsapp_phone=phone)
            db.session.add(trial_record)

        try:
            db.session.commit()
            return restaurant, None
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating restaurant from setup: {e}")
            return None, 'Error al crear la cuenta. Inténtalo de nuevo.'

    # ── Mercado Pago ────────────────────────────────────────

    @staticmethod
    def get_plan_info(plan_key):
        """Return display-friendly plan info dict.

        Matches the original format: name includes 'Plan ' prefix,
        price is a formatted Colombian-style string (e.g. '30.000').
        """
        limits = get_plan_limits(plan_key)
        return {
            'name': f"Plan {limits['name']}",
            'price': f"{limits['price_cop']:,}".replace(',', '.'),
            'price_raw': limits['price_cop'],
            'has_ai_tokens': limits.get('has_ai_tokens', False),
            'ai_tokens': AI_TOKEN_LIMITS.get(plan_key, 0),
        }

    @staticmethod
    def build_mp_preference_data(plan_key, restaurant_id, base_url):
        """
        Build the preference data dict for MercadoPago SDK.
        Returns (preference_data, plan_info).
        """
        plan_info = AuthService.get_plan_info(plan_key)
        preference_data = {
            "items": [
                {
                    "title": f"Suscripción Velzia - {plan_info['name']}",
                    "quantity": 1,
                    "unit_price": float(plan_info['price_raw']),
                    "currency_id": "COP",
                }
            ],
            "back_urls": {
                "success": f"{base_url}/payment-callback",
                "failure": f"{base_url}/payment",
                "pending": f"{base_url}/payment-callback",
            },
            "auto_return": "approved",
            "external_reference": f"{restaurant_id}:{plan_key}",
        }
        return preference_data, plan_info

    @staticmethod
    def create_mp_preference(sdk, preference_data):
        """
        Create a MercadoPago checkout preference.
        Returns (checkout_url, None) or (None, error_message).
        """
        try:
            current_app.logger.debug(f"MP PREFERENCE DATA: {preference_data}")
            preference_response = sdk.preference().create(preference_data)
            if preference_response.get("status") not in (200, 201):
                error_body = preference_response.get("response", {})
                error_msg = error_body.get("message", "Error desconocido de Mercado Pago")
                current_app.logger.error(f"MP ERROR {preference_response.get('status')}: {error_body}")
                return None, error_msg
            preference = preference_response["response"]
            checkout_url = preference.get("init_point")
            return checkout_url, None
        except Exception as e:
            current_app.logger.error(f"Error creating MP preference: {e}")
            return None, "Error al conectar con la pasarela de pago. Inténtalo de nuevo."

    @staticmethod
    def process_payment_callback(status, restaurant_id, plan_type=None):
        """
        Process a payment callback from MercadoPago.

        Returns:
            (restaurant, user, is_renewal_used)
            On success: (restaurant_obj, user_obj_or_None, bool)
            On failure: (None, None, False)
        """
        if status not in ('approved', 'pending'):
            return None, None, False

        restaurant = Restaurant.query.get(restaurant_id)
        if not restaurant:
            return None, None, False

        if status == 'approved':
            restaurant.is_active = True
            if plan_type and plan_type in ('emprendedor', 'crecimiento', 'elite'):
                restaurant.plan_type = plan_type
            db.session.commit()

        sanitize_restaurant_limits(restaurant)

        user = User.query.filter_by(restaurant_id=restaurant.id).first()
        return restaurant, user, True

    @staticmethod
    def process_mp_webhook_payment(payment_id, access_token):
        """
        Process a MercadoPago webhook payment notification (idempotent).

        Returns a dict with keys (restaurant_id, plan_type) if action was taken,
        or None if no action was required.
        """
        sdk = mercadopago.SDK(access_token)
        payment_info = sdk.payment().get(payment_id)
        payment = payment_info.get("response")

        if not payment or payment.get("status") != "approved":
            return None

        external_ref = payment.get("external_reference")
        if not external_ref:
            return None

        try:
            if ':' in external_ref:
                restaurant_id_str, plan_type = external_ref.split(':', 1)
                restaurant_id = int(restaurant_id_str)
            else:
                restaurant_id = int(external_ref)
                plan_type = None
        except (ValueError, TypeError):
            return None

        restaurant = Restaurant.query.get(restaurant_id)
        if not restaurant:
            return None

        # Activate restaurant
        restaurant.is_active = True
        if plan_type and plan_type in ('emprendedor', 'crecimiento', 'elite'):
            restaurant.plan_type = plan_type

        # Subscription extension with anti-duplicate protection
        now_utc = datetime.now(timezone.utc)
        expires_at = restaurant.subscription_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and (expires_at - now_utc).days > 35:
            pass  # Bounce: already >35d remaining
        else:
            if expires_at and expires_at > now_utc:
                restaurant.subscription_expires_at = expires_at + timedelta(days=30)
            else:
                restaurant.subscription_expires_at = now_utc + timedelta(days=30)
            db.session.commit()

        # Apply limits + reset tokens
        try:
            sanitize_restaurant_limits(restaurant)
            user = User.query.filter_by(restaurant_id=restaurant.id).first()
            if user:
                initialize_or_reset_token_wallet(user, is_reset=True,
                                                  mp_payment_id=payment_id)
        except Exception as e:
            current_app.logger.error(
                f"Webhook: error en sanitize_restaurant_limits o wallet: {e}",
                exc_info=True,
            )
            db.session.rollback()

        return {'restaurant_id': restaurant_id, 'plan_type': plan_type}

    # ── API Auth ────────────────────────────────────────────

    @staticmethod
    def api_login(email, password):
        """
        Authenticate and generate JWT tokens.

        Returns:
            (data_dict, None) or (None, error_dict)
        """
        user, error = AuthService.authenticate(email, password)
        if error:
            return None, error

        if user.restaurant and not user.restaurant.is_active:
            return None, {
                'error_code': 'pending_payment',
                'message': 'Tu suscripción está pendiente de pago.',
                'redirect': '/payment',
            }

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
                'is_active': r.is_active,
            }

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'restaurant_id': user.restaurant_id,
            },
            'restaurant': restaurant_data,
        }, None

    @staticmethod
    def api_register(email, plan_type):
        """
        Initiate a registration flow — creates a JWT with OTP embedded.

        Returns:
            (data_dict, None) or (None, error_dict)
        """
        if not email:
            return None, {'error_code': 'MISSING_EMAIL', 'message': 'Email es requerido'}

        valid_plans = ('trial', 'emprendedor', 'crecimiento', 'elite')
        if plan_type not in valid_plans:
            return None, {'error_code': 'INVALID_PLAN', 'message': 'Plan inválido'}

        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.restaurant:
            return None, {
                'error_code': 'ACCOUNT_EXISTS',
                'message': 'Este email ya tiene una cuenta activa. Por favor inicia sesión.',
            }

        otp = AuthService.generate_otp()

        if existing_user:
            otp_data = {
                'otp': otp,
                'email': email,
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                'plan_type': plan_type,
            }
            temp_token = create_access_token(
                identity=str(existing_user.id),
                additional_claims={'type': 'register_verify', 'otp_data': otp_data},
            )
        else:
            temp_token_data = {
                'email': email,
                'plan_type': plan_type,
                'otp': otp,
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            }
            temp_token = create_access_token(
                identity='register_temp',
                additional_claims={'type': 'register_temp', 'data': temp_token_data},
                expires_delta=timedelta(minutes=10),
            )

        AuthService.send_otp_email(email, otp)

        return {
            'message': 'Se ha enviado un código de verificación a tu email',
            'temp_token': temp_token,
            'existing_user': bool(existing_user),
        }, None

    @staticmethod
    def verify_otp(temp_token, otp_code):
        """
        Verify an OTP code embedded in a JWT token.

        Returns:
            (data_dict, None) or (None, error_dict)
            data_dict contains: message, verified_token, email, plan_type
        """
        if not temp_token or not otp_code:
            return None, {'error_code': 'MISSING_FIELDS',
                          'message': 'Token y código OTP son requeridos'}

        try:
            decoded = decode_token(temp_token)

            # Determine token type and extract data
            if decoded.get('sub') == 'register_temp':
                token_data = decoded.get('data', {})
            elif decoded.get('type') == 'register_verify':
                token_data = decoded.get('otp_data', {})
            else:
                token_data = decoded.get('data', decoded.get('otp_data', {}))
                if not token_data.get('otp'):
                    return None, {'error_code': 'INVALID_TOKEN',
                                  'message': 'Token inválido'}

            expires_at = datetime.fromisoformat(token_data['expires_at'])
            if datetime.now(timezone.utc) > expires_at:
                return None, {'error_code': 'OTP_EXPIRED',
                              'message': 'El código ha expirado'}

            if str(token_data.get('otp')) != str(otp_code):
                return None, {'error_code': 'INVALID_OTP',
                              'message': 'Código incorrecto'}

            email = token_data['email']
            plan_type = token_data['plan_type']

            verify_token = create_access_token(
                identity='register_verified',
                additional_claims={
                    'type': 'register_verified',
                    'data': {'email': email, 'plan_type': plan_type},
                },
                expires_delta=timedelta(minutes=30),
            )

            return {
                'message': 'Código verificado exitosamente',
                'verified_token': verify_token,
                'email': email,
                'plan_type': plan_type,
            }, None

        except Exception as e:
            current_app.logger.error(f"OTP verification error: {e}")
            return None, {'error_code': 'TOKEN_ERROR',
                          'message': 'Token inválido o expirado'}

    @staticmethod
    def api_setup_account(verified_token, account_data):
        """
        Complete account setup via API after OTP verification.

        account_data: { restaurant_name, whatsapp_phone, username, password }

        Returns:
            (data_dict, None) or (None, error_dict)
        """
        if not verified_token:
            return None, {'error_code': 'MISSING_TOKEN',
                          'message': 'Token de verificación requerido'}

        try:
            decoded = decode_token(verified_token)
            if decoded.get('type') != 'register_verified':
                return None, {'error_code': 'INVALID_TOKEN',
                              'message': 'Token inválido'}
            token_data = decoded.get('data', {})
            email = token_data.get('email')
            plan_type = token_data.get('plan_type')
        except Exception:
            return None, {'error_code': 'INVALID_TOKEN',
                          'message': 'Token inválido o expirado'}

        restaurant_name = (account_data.get('restaurant_name') or '').strip()
        whatsapp_phone = (account_data.get('whatsapp_phone') or '').strip()
        username = (account_data.get('username') or '').strip()
        password = account_data.get('password', '')

        if not restaurant_name or not whatsapp_phone or not username or not password:
            return None, {'error_code': 'MISSING_FIELDS',
                          'message': 'Todos los campos son requeridos'}

        pwd_error = AuthService.validate_password(password)
        if pwd_error:
            return None, {'error_code': 'WEAK_PASSWORD', 'message': pwd_error}

        slug = AuthService.generate_slug(restaurant_name)
        if AuthService.is_reserved_slug(slug):
            return None, {
                'error_code': 'RESERVED_NAME',
                'message': f'El nombre "{restaurant_name}" está reservado. Elige otro nombre.',
            }

        slug = AuthService.ensure_unique_slug(slug)
        is_trial = (plan_type == 'trial')

        if is_trial:
            blocked, msg = AuthService.check_trial_eligibility(email, whatsapp_phone)
            if blocked:
                return None, {'error_code': 'TRIAL_USED', 'message': msg}

            trial_expires = datetime.now(timezone.utc) + timedelta(days=10)
            restaurant = Restaurant(
                name=restaurant_name, slug=slug, whatsapp_phone=whatsapp_phone,
                plan_type='trial', is_active=True,
                subscription_expires_at=trial_expires, is_open=True,
                has_used_trial=False,
            )
        else:
            restaurant = Restaurant(
                name=restaurant_name, slug=slug, whatsapp_phone=whatsapp_phone,
                plan_type=plan_type, is_active=False,
                subscription_expires_at=None, is_open=True,
                has_used_trial=False,
            )

        db.session.add(restaurant)
        db.session.flush()

        user = User(email=email, username=username, restaurant_id=restaurant.id)
        user.set_password(password)
        db.session.add(user)

        if is_trial:
            db.session.add(TrialHistory(email=email, whatsapp_phone=whatsapp_phone))

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"API setup account error: {e}")
            return None, {'error_code': 'SETUP_ERROR',
                          'message': 'Error al crear la cuenta. Inténtalo de nuevo.'}

        if is_trial:
            initialize_or_reset_token_wallet(user)

        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {'id': user.id, 'username': user.username, 'email': user.email},
            'restaurant': {
                'id': restaurant.id, 'name': restaurant.name,
                'slug': restaurant.slug, 'plan_type': restaurant.plan_type,
            },
        }, None

    @staticmethod
    def api_refresh_token(refresh_token):
        """
        Refresh an access JWT using a refresh token.

        Returns:
            (data_dict, None) or (None, error_dict)
        """
        if not refresh_token:
            return None, {'error_code': 'MISSING_TOKEN',
                          'message': 'Refresh token requerido'}

        try:
            decoded = decode_token(refresh_token)
            user_id = decoded.get('sub')
            if not user_id:
                return None, {'error_code': 'INVALID_TOKEN',
                              'message': 'Token inválido'}

            user = User.query.get(user_id)
            if not user:
                return None, {'error_code': 'USER_NOT_FOUND',
                              'message': 'Usuario no encontrado'}

            new_access_token = create_access_token(identity=str(user.id))

            restaurant_data = None
            if user.restaurant:
                r = user.restaurant
                restaurant_data = {
                    'id': r.id, 'name': r.name, 'slug': r.slug,
                    'plan_type': r.plan_type, 'is_open': r.is_open,
                    'is_active': r.is_active,
                }

            return {
                'access_token': new_access_token,
                'user': {'id': user.id, 'username': user.username, 'email': user.email},
                'restaurant': restaurant_data,
            }, None

        except Exception as e:
            current_app.logger.error(f"Token refresh error: {e}")
            return None, {'error_code': 'TOKEN_ERROR',
                          'message': 'Token inválido o expirado'}

    @staticmethod
    def get_plans_config():
        """
        Return full plans configuration with limits and top-up packs.
        """
        plan_types = ['trial', 'emprendedor', 'crecimiento', 'elite']
        plans_config = {}
        for pt in plan_types:
            limits = get_plan_limits(pt)
            max_prods = limits['max_products']
            plans_config[pt] = {
                'type': pt,
                'name': limits['name'],
                'price_cop': limits['price_cop'],
                'duration_days': limits['duration_days'],
                'features': {
                    'max_products': 'ilimitado' if max_prods == float('inf') else max_prods,
                    'has_qr': limits['has_qr'],
                    'has_table_qr': limits['has_table_qr'],
                    'has_modifiers': limits['has_modifiers'],
                    'has_status_management': limits['has_status_management'],
                    'ai_tokens': AI_TOKEN_LIMITS.get(pt, 0),
                },
            }

        top_up_packs = [{'id': k, **v} for k, v in TOP_UP_PACKS.items()]

        return {
            'plans': list(plans_config.values()),
            'top_up_packs': top_up_packs,
        }

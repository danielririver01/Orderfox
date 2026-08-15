"""
AuthService — Business logic for authentication and account operations.
Shared by web routes (auth_bp) and API routes (api_auth_bp).

Pattern: @staticmethod methods returning (result, None) / (None, error_dict).
"""
from datetime import datetime, timedelta, timezone
import re
import secrets
import unicodedata
from flask import current_app, render_template
from werkzeug.security import generate_password_hash

from app.models import db, User, Restaurant, TrialHistory, AITokenWallet, PreRegistration
from app.utils.subscription import (
    initialize_or_reset_token_wallet,
    AI_TOKEN_LIMITS,
)
from app.utils.constants import RESERVED_SLUGS
from app.services.mail_service import send_email
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token


class AuthService:
    """Business logic for authentication and account operations."""

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def get_user(user_id):
        """Return User by ID or None."""
        return User.query.get(user_id)

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

                # Bug 3: un correo que ya usó el trial gratuito NO puede recibir
                # otro. Se consulta TrialHistory ANTES de crear el usuario, para
                # no "regalar" trial en el flujo Clerk (donde el check de
                # setup_account llega demasiado tarde).
                if selected_plan == 'trial':
                    already_used = TrialHistory.query.filter_by(email=email).first()
                    if already_used:
                        return None, False, {
                            'error_code': 'TRIAL_ALREADY_USED',
                            'message': 'Ya usaste tu período de prueba gratuito. Elige un plan para continuar.'
                        }

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

    # ── Plan Selection ──────────────────────────────────────

    @staticmethod
    def save_plan_selection(email, plan):
        """
        Save or update a pre-registration plan selection.
        Returns (pre_reg, None) or (None, error_dict).
        """
        valid_plans = ['trial', 'emprendedor', 'crecimiento', 'elite']
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
            trial_expires_at = datetime.now(timezone.utc) + timedelta(days=60)
            restaurant = Restaurant(
                name=restaurant_name,
                slug=slug,
                whatsapp_phone=phone,
                plan_type='trial',
                is_active=True,
                subscription_expires_at=trial_expires_at,
                is_open=True,
                has_used_trial=True,  # Bug 3: marca que el trial fue usado (antes quedaba False, código muerto)
                ntfy_topic=secrets.token_hex(16),
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
                ntfy_topic=secrets.token_hex(16),
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

    @staticmethod
    def send_welcome_email(restaurant, user):
        """Email de bienvenida tras el registro exitoso con plan trial.

        Se dispara justo después de crear el restaurante en DB (lo llama la
        ruta de registro). No bloquea el flujo: si el envío falla (SMTP, red),
        el registro continúa igual; el envío real lo hace mail_service.
        """
        if not restaurant or not user or not user.email:
            return False

        base_url = current_app.config.get('BASE_URL', '')
        dashboard_url = f"{base_url}/dashboard/"

        html = render_template(
            'email/welcome.html',
            restaurant_name=restaurant.name,
            dashboard_url=dashboard_url,
        )
        text = (
            f'¡Bienvenido a Velzia, {restaurant.name}!\n\n'
            'Tu restaurante ya está listo. Tienes 60 días para explorar todo '
            'lo que Velzia puede hacer por tu negocio: tu menú digital, '
            'pedidos por WhatsApp y todas las herramientas operativas.\n\n'
            f'Sube tu primer producto al menú: {dashboard_url}\n\n'
            'Un abrazo,\nDaniel — Fundador de Velzia'
        )

        return send_email(
            to=user.email,
            subject=f'¡Bienvenido a Velzia, {restaurant.name}!',
            html_body=html,
            text_body=text,
        )

    # ── Mercado Pago (delegado a SubscriptionService) ────────
    # Métodos movidos a app/services/subscription_service.py:
    #   get_plan_info, get_plans_config, build_mp_preference_data,
    #   create_mp_preference, reserve_coupon, apply_coupon,
    #   process_payment_callback, process_mp_webhook_payment

    # ── Core Auth ───────────────────────────────────────────

    @staticmethod
    def authenticate(email, password):
        """
        Authenticate a user by email and password.

        Returns:
            (user, None) on success,
            (None, error_dict) on failure.
        """
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return None, {'error_code': 'INVALID_CREDENTIALS', 'message': 'Credenciales inválidas'}
        return user, None

    # ── Clerk Verification ─────────────────────────────────

    @staticmethod
    def verify_clerk_session(session_id, clerk_id, email):
        """
        Verify a Clerk session by calling the Clerk API directly.

        Returns:
            (verified_email, None) on success,
            (None, error_dict) on failure.
        """
        import requests
        clerk_secret = current_app.config.get('CLERK_SECRET_KEY')
        if not clerk_secret:
            return None, {'error_code': 'CLERK_NOT_CONFIGURED',
                          'message': 'Clerk secret not configured'}

        try:
            session_resp = requests.get(
                f"https://api.clerk.com/v1/sessions/{session_id}",
                headers={"Authorization": f"Bearer {clerk_secret}"},
                timeout=5
            )

            if session_resp.status_code != 200:
                return None, {'error_code': 'INVALID_SESSION',
                              'message': 'Invalid or inactive session'}

            session_data = session_resp.json()
            if session_data.get('status') != 'active':
                return None, {'error_code': 'INVALID_SESSION',
                              'message': 'Invalid or inactive session'}

            # Seguridad: la sesión debe pertenecer al clerk_id declarado por el
            # cliente. Sin esto, cualquiera con una sesión Clerk activa (la suya)
            # podía enviar el clerk_id + email de otra persona y secuestrar su
            # cuenta local (GET /v1/sessions/{id} devuelve user_id en el objeto).
            if session_data.get('user_id') != clerk_id:
                return None, {'error_code': 'SESSION_USER_MISMATCH',
                              'message': 'La sesión no pertenece a este usuario'}

            response = requests.get(
                f"https://api.clerk.com/v1/users/{clerk_id}",
                headers={"Authorization": f"Bearer {clerk_secret}"},
                timeout=5
            )

            if response.status_code != 200:
                return None, {'error_code': 'INVALID_USER',
                              'message': 'Invalid Clerk user'}

            clerk_user_data = response.json()
            verified_email = next(
                (e['email_address'] for e in clerk_user_data.get('email_addresses', [])
                 if e['id'] == clerk_user_data.get('primary_email_address_id')),
                None
            )

            if not verified_email:
                all_emails = [e['email_address'] for e in clerk_user_data.get('email_addresses', [])]
                if email.lower() in [e.lower() for e in all_emails]:
                    verified_email = email

            if not verified_email or verified_email.lower() != email.lower():
                return None, {'error_code': 'EMAIL_MISMATCH',
                              'message': 'Email mismatch or not verified'}

            return verified_email, None

        except Exception as e:
            current_app.logger.error(f"Error verifying Clerk user: {e}")
            return None, {'error_code': 'VERIFICATION_FAILED',
                          'message': 'Verification failed'}

    # ── AI Scan Token ──────────────────────────────────────

    @staticmethod
    def delete_clerk_user(clerk_id):
        """
        Elimina un usuario de Clerk por completo (DELETE /v1/users/{clerk_id}).

        Devuelve (True, None) si Clerk confirmó la eliminación (200 o 404:
        el 404 significa que ya no existía, que es el estado deseado) o
        (False, mensaje_error) si Clerk rechazó la llamada.
        """
        if not clerk_id:
            return True, None

        import requests
        clerk_secret = current_app.config.get('CLERK_SECRET_KEY')
        if not clerk_secret:
            return False, 'Clerk no está configurado. No se pudo eliminar la cuenta.'

        try:
            response = requests.delete(
                f"https://api.clerk.com/v1/users/{clerk_id}",
                headers={"Authorization": f"Bearer {clerk_secret}"},
                timeout=10
            )
            if response.status_code in (200, 404):
                return True, None
            current_app.logger.error(
                f"Clerk delete user failed: {response.status_code} {response.text[:300]}"
            )
            return False, 'No se pudo eliminar tu cuenta en el sistema de autenticación. Inténtalo de nuevo.'
        except Exception as e:
            current_app.logger.error(f"Error deleting Clerk user: {e}")
            return False, 'Error de red al eliminar tu cuenta. Inténtalo de nuevo.'

    @staticmethod
    def generate_ai_scan_token(user, app_config):
        """
        Generate a signed JWT token for Scanner IA redirect.

        Returns the signed token string.
        """
        import jwt as pyjwt
        token_payload = {
            'iss': app_config.get('BASE_URL', 'https://velzia.co'),
            'clerk_id': user.clerk_id,
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.now(timezone.utc) + timedelta(minutes=5),
            'iat': datetime.now(timezone.utc)
        }
        signed_token = pyjwt.encode(
            token_payload,
            app_config['SECRET_KEY'],
            algorithm='HS256'
        )
        return signed_token

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

        iss = current_app.config.get('BASE_URL', 'https://velzia.co')
        access_token = create_access_token(identity=str(user.id), additional_claims={'iss': iss})
        refresh_token = create_refresh_token(identity=str(user.id), additional_claims={'iss': iss})

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

            iss = current_app.config.get('BASE_URL', 'https://velzia.co')
            new_access_token = create_access_token(identity=str(user.id), additional_claims={'iss': iss})

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

    # get_plans_config movido a SubscriptionService

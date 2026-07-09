"""
AuthService — Business logic for authentication and account operations.
Shared by web routes (auth_bp) and API routes (api_auth_bp).

Pattern: @staticmethod methods returning (result, None) / (None, error_dict).
"""
from datetime import datetime, timedelta, timezone
import re
import secrets
import unicodedata
from flask import current_app
from werkzeug.security import generate_password_hash

from app.models import db, User, Restaurant, TrialHistory, AITokenWallet, PreRegistration
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

    # ── Core Auth ───────────────────────────────────────────

    @staticmethod
    def authenticate(email, password):
        """
        Authenticate a user by email and password.

        Returns:
            (user, None) on success,
            (None, error_message_string) on failure.
        """
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return None, 'Credenciales inválidas'
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

            if session_resp.status_code != 200 or session_resp.json().get('status') != 'active':
                return None, {'error_code': 'INVALID_SESSION',
                              'message': 'Invalid or inactive session'}

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
    def generate_ai_scan_token(user, app_config):
        """
        Generate a signed JWT token for Scanner IA redirect.

        Returns the signed token string.
        """
        import jwt as pyjwt
        token_payload = {
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

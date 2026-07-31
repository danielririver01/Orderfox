"""
SubscriptionService — Planes, MercadoPago preferences, webhooks y cupones de descuento.
"""
import json
import threading
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError
from flask import current_app
from app import db
from app.models import Restaurant, User, DiscountCoupon
from app.utils.subscription import (
    get_plan_limits,
    AI_TOKEN_LIMITS,
    TOP_UP_PACKS,
    sanitize_restaurant_limits,
    initialize_or_reset_token_wallet,
)
import mercadopago


def _fire_n8n_reward(url: str, body: bytes, app):
    """Envía el payload a n8n en segundo plano (fire-and-forget)."""
    with app.app_context():
        try:
            req = Request(url, data=body, headers={'Content-Type': 'application/json'})
            urlopen(req, timeout=5)
            current_app.logger.info(f"N8N reward triggered: {body.decode()[:100]}")
        except URLError as e:
            current_app.logger.warning(f"N8N reward failed: {e.reason}")


class SubscriptionService:
    """Lógica de suscripciones, pagos MP y descuentos."""

    # ── Plan Info ───────────────────────────────────────────

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
            'ai_tokens_unlimited': False,
        }

    @staticmethod
    def get_plans_config():
        """Return full plans configuration with limits and top-up packs."""
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

    # ── MercadoPago Preferences ─────────────────────────────

    @staticmethod
    def build_mp_preference_data(plan_key, restaurant_id, base_url):
        """
        Build the preference data dict for MercadoPago SDK.
        Applies FIFO discount coupon if available.
        Returns (preference_data, plan_info, coupon_or_None).
        """
        plan_info = SubscriptionService.get_plan_info(plan_key)
        unit_price = float(plan_info['price_raw'])

        coupon = DiscountCoupon.query.filter_by(
            restaurant_id=restaurant_id,
            status='pending',
        ).order_by(DiscountCoupon.created_at.asc()).first()
        applied_discount = None

        if coupon and coupon.expires_at > datetime.now(timezone.utc):
            unit_price = round(unit_price * (1 - coupon.percentage / 100), 2)
            applied_discount = coupon
        elif coupon and coupon.expires_at <= datetime.now(timezone.utc):
            coupon.status = 'expired'
            db.session.commit()
            applied_discount = None

        preference_data = {
            "items": [
                {
                    "title": f"Suscripción Velzia - {plan_info['name']}",
                    "quantity": 1,
                    "unit_price": unit_price,
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
        return preference_data, plan_info, applied_discount

    @staticmethod
    def create_mp_preference(sdk, preference_data):
        """
        Create a MercadoPago checkout preference.
        Returns (checkout_url, preference_id, None) or (None, None, error_message).
        """
        try:
            current_app.logger.debug(f"MP PREFERENCE DATA: {preference_data}")
            preference_response = sdk.preference().create(preference_data)
            if preference_response.get("status") not in (200, 201):
                error_body = preference_response.get("response", {})
                error_msg = error_body.get("message", "Error desconocido de Mercado Pago")
                current_app.logger.error(f"MP ERROR {preference_response.get('status')}: {error_body}")
                return None, None, error_msg
            preference = preference_response["response"]
            checkout_url = preference.get("init_point")
            preference_id = preference.get('id')
            return checkout_url, preference_id, None
        except Exception as e:
            current_app.logger.error(f"Error creating MP preference: {e}")
            return None, None, "Error al conectar con la pasarela de pago. Inténtalo de nuevo."

    # ── Descuentos (Coupons) ────────────────────────────────

    @staticmethod
    def reserve_coupon(coupon: DiscountCoupon, preference_id: str) -> None:
        if not coupon:
            return
        DiscountCoupon.query.filter_by(
            restaurant_id=coupon.restaurant_id,
            status='reserved',
        ).update({'status': 'pending', 'preference_id': None, 'reserved_at': None})
        coupon.status = 'reserved'
        coupon.preference_id = preference_id
        coupon.reserved_at = datetime.now(timezone.utc)
        db.session.commit()

    @staticmethod
    def apply_coupon(coupon: DiscountCoupon, payment_id: str) -> None:
        if not coupon:
            return
        coupon.status = 'applied'
        coupon.applied_to_payment_id = payment_id
        coupon.applied_at = datetime.now(timezone.utc)
        db.session.commit()

    @staticmethod
    def _finalize_payment(restaurant, plan_type, payment_id, preference_id=None, n8n_payload=None):
        """
        Lógica compartida entre webhook y callback: consume el cupón reservado,
        extiende la suscripción por la duración del plan y dispara n8n.
        Idempotente por pago: el disparo a n8n ocurre solo la primera vez.
        """
        from app.models import AITokenTransaction

        if AITokenTransaction.query.filter_by(
            mp_payment_id=payment_id,
            type='topup_plan',
        ).first():
            return

        coupon = None
        if preference_id:
            coupon = DiscountCoupon.query.filter_by(
                preference_id=preference_id,
                status='reserved',
            ).first()
        if not coupon:
            coupon = DiscountCoupon.query.filter_by(
                restaurant_id=restaurant.id,
                status='reserved',
            ).order_by(DiscountCoupon.reserved_at.desc()).first()
        if coupon:
            SubscriptionService.apply_coupon(coupon, payment_id)

        duration_days = get_plan_limits(plan_type or restaurant.plan_type).get('duration_days', 30)
        now_utc = datetime.now(timezone.utc)
        expires_at = restaurant.subscription_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at > now_utc:
            restaurant.subscription_expires_at = expires_at + timedelta(days=duration_days)
        else:
            restaurant.subscription_expires_at = now_utc + timedelta(days=duration_days)
        db.session.commit()

        if n8n_payload and n8n_payload.get('url'):
            body = json.dumps({
                'external_reference': n8n_payload.get('external_reference'),
                'user_id': n8n_payload.get('user_id'),
                'payer': {'email': n8n_payload.get('payer_email', '')},
                'streak_bonus_claim_id': n8n_payload.get('streak_bonus_claim_id'),
            }).encode()
            threading.Thread(
                target=_fire_n8n_reward,
                args=(n8n_payload['url'], body, current_app._get_current_object()),
                daemon=True,
            ).start()

    # ── Webhooks / Callbacks ────────────────────────────────

    @staticmethod
    def process_payment_callback(status, restaurant_id, plan_type=None, payment_id=None, n8n_payload=None):
        """
        Process a payment callback from MercadoPago.
        Returns:
            (restaurant, user, is_renewal_used)
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

            if payment_id:
                SubscriptionService._finalize_payment(
                    restaurant, plan_type or restaurant.plan_type, payment_id,
                    n8n_payload=n8n_payload,
                )

        sanitize_restaurant_limits(restaurant)

        user = User.query.filter_by(restaurant_id=restaurant.id).first()
        return restaurant, user, True

    @staticmethod
    def process_mp_webhook_payment(payment_id, access_token, n8n_payload=None):
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

        # Apply discount coupon if one was reserved for this preference
        # y extiende la suscripción por la duración del plan (idempotente).
        SubscriptionService._finalize_payment(
            restaurant,
            plan_type,
            payment_id,
            preference_id=payment.get('preference_id'),
            n8n_payload=n8n_payload,
        )

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

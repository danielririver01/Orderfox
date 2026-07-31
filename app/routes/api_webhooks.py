"""
api_webhooks.py — Endpoints de webhooks para pasarelas de pago y servicios externos.

Prioridad: verificación de firma HMAC + idempotencia para prevenir
reenvíos maliciosos y race conditions.
"""

import logging
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import URLError

from flask import Blueprint, request, jsonify, current_app

from werkzeug.security import generate_password_hash

from app.services.subscription_service import SubscriptionService
from app.services.token_service import TokenService
from app import db
from app.models import AITokenTransaction, User, Restaurant
from app.utils.mp_webhook import extract_mp_signature, verify_mp_signature
from app.utils.subscription import TOP_UP_PACKS

api_webhooks_bp = Blueprint('api_webhooks', __name__, url_prefix='/api/v1/webhooks')

logger = logging.getLogger(__name__)


@api_webhooks_bp.route('/clerk', methods=['POST'])
def clerk_webhook():
    """
    Webhook de Clerk para sincronización de usuarios.
    Verifica firma Svix, maneja: user.created, user.updated, user.deleted.
    """
    wh_secret = current_app.config.get('CLERK_WEBHOOK_SECRET')
    if not wh_secret:
        logger.error("CLERK WEBHOOK: CLERK_WEBHOOK_SECRET no configurado")
        return jsonify({'success': False, 'error': 'webhook_not_configured'}), 503

    # Lazy import: svix puede no estar instalado (Docker sin --no-cache-dir)
    try:
        from svix.webhooks import Webhook, WebhookVerificationError
    except ImportError:
        logger.error("CLERK WEBHOOK: svix no instalado. Ejecuta: pip install svix")
        return jsonify({'success': False, 'error': 'svix_not_installed'}), 503

    # Verificar firma Svix
    headers = {
        'svix-id': request.headers.get('svix-id'),
        'svix-timestamp': request.headers.get('svix-timestamp'),
        'svix-signature': request.headers.get('svix-signature'),
    }
    if not all(headers.values()):
        return jsonify({'success': False, 'error': 'missing_svix_headers'}), 401

    try:
        wh = Webhook(wh_secret)
        payload = wh.verify(request.get_data(), headers)
    except WebhookVerificationError:
        logger.warning("CLERK WEBHOOK: Firma Svix inválida")
        return jsonify({'success': False, 'error': 'invalid_signature'}), 401

    event_type = payload.get('type')
    data = payload.get('data', {})

    clerk_id = data.get('id')
    if not clerk_id:
        return jsonify({'success': False, 'error': 'missing_user_id'}), 400

    email = ''
    email_addresses = data.get('email_addresses', [])
    if email_addresses:
        email = email_addresses[0].get('email_address', '')

    username = data.get('username') or data.get('first_name') or email.split('@')[0]

    if event_type == 'user.created':
        existing = User.query.filter_by(clerk_id=clerk_id).first()
        if existing:
            logger.info(f"CLERK WEBHOOK: user.created para clerk_id={clerk_id} ya existe, saltando")
            return jsonify({'success': True, 'status': 'already_exists'}), 200

        user = User(
            clerk_id=clerk_id,
            email=email,
            username=username,
            password=generate_password_hash(str(clerk_id))
        )
        db.session.add(user)
        db.session.commit()
        logger.info(f"CLERK WEBHOOK: Usuario {clerk_id} creado con email={email}")
        return jsonify({'success': True, 'status': 'user_created'}), 201

    elif event_type == 'user.updated':
        user = User.query.filter_by(clerk_id=clerk_id).first()
        if not user:
            user = User(
                clerk_id=clerk_id,
                email=email,
                username=username,
                password=generate_password_hash(str(clerk_id))
            )
            db.session.add(user)
            logger.info(f"CLERK WEBHOOK: user.updated pero no existía, creado clerk_id={clerk_id}")
        else:
            if email:
                user.email = email
            if username:
                user.username = username
        db.session.commit()
        return jsonify({'success': True, 'status': 'user_updated'}), 200

    elif event_type == 'user.deleted':
        user = User.query.filter_by(clerk_id=clerk_id).first()
        if user:
            db.session.delete(user)
            db.session.commit()
            logger.info(f"CLERK WEBHOOK: Usuario {clerk_id} eliminado")
            return jsonify({'success': True, 'status': 'user_deleted'}), 200
        logger.info(f"CLERK WEBHOOK: user.deleted pero no existía en DB, clerk_id={clerk_id}")
        return jsonify({'success': True, 'status': 'not_found'}), 200

    logger.debug(f"CLERK WEBHOOK: Evento ignorado {event_type}")
    return jsonify({'success': True, 'status': 'ignored'}), 200


def _fire_n8n_reward(url: str, body: bytes, app):
    """Envía el payload a n8n en segundo plano (fire-and-forget)."""
    with app.app_context():
        try:
            req = Request(url, data=body, headers={'Content-Type': 'application/json'})
            urlopen(req, timeout=5)
            logger.info(f"N8N reward triggered: {body.decode()[:100]}")
        except URLError as e:
            logger.warning(f"N8N reward failed: {e.reason}")


def _payment_already_processed(data_id: str) -> bool:
    """Chequeo de idempotencia unificado: True si este payment_id ya fue procesado
    como suscripción (topup_plan) o como top-up de tokens (topup_purchase)."""
    if not data_id:
        return False
    return AITokenTransaction.query.filter(
        AITokenTransaction.mp_payment_id == data_id,
        AITokenTransaction.type.in_(['topup_plan', 'topup_purchase'])
    ).first() is not None


@api_webhooks_bp.route('/mercadopago', methods=['POST'])
def mercadopago_webhook():
    """Webhook de Mercado Pago (Webhooks API).

    Verifica firma HMAC-SHA256 del header `x-signature`, procesa pagos
    aprobados y acredita tokens. Es idempotente: si el `data.id` ya fue
    procesado, retorna 200 sin re-procesar.
    """
    try:
        body = request.get_json(silent=True) or {}
        headers = request.headers

        # Extraer data.id del body
        data_id = None
        if body.get('data') and body['data'].get('id'):
            data_id = str(body['data']['id'])
        if not data_id:
            data_id = str(body.get('id') or '')

        # Extraer y verificar firma
        ts, v1 = extract_mp_signature(headers)
        webhook_secret = current_app.config.get('MP_WEBHOOK_SECRET')

        if webhook_secret:
            if not data_id:
                logger.warning("WEBHOOK MP: Falta data.id en el payload")
                return jsonify({'success': False, 'error': 'missing_data_id'}), 400
            if not verify_mp_signature(data_id, ts, v1, webhook_secret):
                logger.warning(f"WEBHOOK MP: Firma inválida para data_id={data_id}")
                return jsonify({'success': False, 'error': 'invalid_signature'}), 401
        else:
            # Si no hay secret configurado, rechazamos el webhook en vez de
            # aceptarlo sin verificar (fail-closed).
            logger.error("WEBHOOK MP: MP_WEBHOOK_SECRET no configurado")
            return jsonify({'success': False, 'error': 'webhook_not_configured'}), 503

        # Idempotencia: si ya procesamos este data.id, saltar
        if _payment_already_processed(data_id):
            logger.info(f"WEBHOOK MP: data_id={data_id} ya procesado. Saltando.")
            return jsonify({'success': True, 'status': 'already_processed'}), 200

        # Procesar el pago (solo si es tipo payment)
        action_type = body.get('type', '')
        if action_type == 'payment' or body.get('action', '') == 'payment.created':
            payment_id = data_id
            access_token = current_app.config.get('MP_ACCESS_TOKEN')
            if not access_token:
                logger.error("WEBHOOK MP: MP_ACCESS_TOKEN no configurado")
                return jsonify({'success': False, 'error': 'server_config'}), 500

            # Obtener info del pago desde la API de MP para leer external_reference
            import mercadopago
            sdk = mercadopago.SDK(access_token)
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get("response")

            if payment and payment.get("status") == "approved":
                external_ref = payment.get("external_reference", "")

                if external_ref.startswith("token_topup:"):
                    # ── Token top-up flow ──
                    try:
                        _, user_id_str, pack_key = external_ref.split(":")
                        user = User.query.get(int(user_id_str))
                        pack = TOP_UP_PACKS.get(pack_key)
                        if user and pack:
                            result, error = TokenService.credit_topup_purchase(
                                user, pack, payment_id
                            )
                            if not error:
                                logger.info(
                                    f"WEBHOOK MP: Top-up {pack['tokens']} tokens para "
                                    f"usuario {user.id}"
                                )
                                return jsonify({
                                    'success': True,
                                    'status': 'topup_credited',
                                }), 200
                    except (ValueError, TypeError):
                        pass
                    logger.warning(
                        f"WEBHOOK MP: token_topup inválido: {external_ref}"
                    )
                    return jsonify({'success': True, 'status': 'topup_ignored'}), 200

                # ── Detect renewal before processing ──
                from datetime import datetime, timezone
                was_renewal = False
                months_active = 0
                try:
                    ext_ref = external_ref
                    if ':' in ext_ref:
                        rid_str = ext_ref.split(':', 1)[0]
                    else:
                        rid_str = ext_ref
                    r = db.session.get(Restaurant, int(rid_str))
                    if r and r.is_active and r.subscription_expires_at:
                        expires = r.subscription_expires_at
                        if expires.tzinfo is None:
                            expires = expires.replace(tzinfo=timezone.utc)
                        if expires > datetime.now(timezone.utc):
                            was_renewal = True
                            days = (datetime.now(timezone.utc) - r.created_at).days if r.created_at else 0
                            months_active = max(1, days // 30)
                except Exception:
                    logger.warning("Error detectando renovación", exc_info=True)

                # ── Subscription activation flow ──
                result = SubscriptionService.process_mp_webhook_payment(
                    payment_id, access_token
                )
                if result:
                    logger.info(
                        f"WEBHOOK MP: Restaurante {result.get('restaurant_id')} activado"
                    )
                    # Evaluar logros
                    from app.models import User
                    from app.services.achievement_engine import evaluate as eval_achievement
                    try:
                        u = User.query.filter_by(restaurant_id=result['restaurant_id']).first()
                        if u:
                            if was_renewal:
                                eval_achievement(u.id, 'subscription_renewed', {'months_active': months_active})
                            else:
                                eval_achievement(u.id, 'subscription_activated')
                    except Exception:
                        logger.warning("Error evaluando logros de suscripción", exc_info=True)

                    # ── Sistema de Fidelización Velzia (Streak) ──
                    from app.services.streak_service import bump_streak, reset_streak
                    from app.services.reward_service import generate_streak_reward
                    from app.models import RewardClaim
                    restaurant_id = result.get('restaurant_id')
                    streak_bonus_claim_id = None
                    try:
                        r = db.session.get(Restaurant, restaurant_id)
                        if r and not was_renewal and r.subscription_expires_at:
                            expires = r.subscription_expires_at
                            if expires.tzinfo is None:
                                expires = expires.replace(tzinfo=timezone.utc)
                            if expires < datetime.now(timezone.utc):
                                reset_streak(restaurant_id)

                        streak_result = bump_streak(restaurant_id, payment_id)
                        if not streak_result.get('duplicate') and streak_result.get('bonus_tier') and u:
                            bonus = generate_streak_reward(streak_result['bonus_tier'])
                            if bonus:
                                bonus_claim = RewardClaim(
                                    user_id=u.id,
                                    restaurant_id=restaurant_id,
                                    short_code=__import__('secrets').token_urlsafe(16),
                                    token=str(__import__('uuid').uuid4()),
                                    plan_key=r.plan_type if r else 'emprendedor',
                                    rarity=bonus['rarity'],
                                    reward_type=bonus['type'],
                                    reward_value=bonus.get('value'),
                                    reward_label=bonus['label'],
                                    status='pending',
                                )
                                db.session.add(bonus_claim)
                                db.session.commit()
                                streak_bonus_claim_id = bonus_claim.id
                                logger.info(
                                    'Streak bonus: id=%d tier=%d label=%s para user=%d',
                                    bonus_claim.id, streak_result['bonus_tier'], bonus['label'], u.id,
                                )
                    except Exception:
                        logger.warning("Error procesando streak", exc_info=True)

                    # Disparar Sorpresa Velzia en segundo plano
                    n8n_url = current_app.config.get('N8N_REWARD_URL')
                    if n8n_url and external_ref:
                        payer_email = payment.get('payer', {}).get('email', '')
                        body = json.dumps({
                            'external_reference': external_ref,
                            'user_id': u.id if u else None,
                            'payer': {'email': payer_email or ''},
                            'streak_bonus_claim_id': streak_bonus_claim_id,
                        }).encode()
                        threading.Thread(
                            target=_fire_n8n_reward,
                            args=(n8n_url, body, current_app._get_current_object()),
                            daemon=True
                        ).start()
                    return jsonify({
                        'success': True,
                        'status': 'processed',
                        'restaurant_id': restaurant_id,
                    }), 200

        return jsonify({'success': True, 'status': 'no_action'}), 200

    except Exception as e:
        logger.error(f"WEBHOOK MP ERROR: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'internal_error'}), 500


@api_webhooks_bp.route('/achievements/trigger', methods=['POST'])
def trigger_achievement():
    """
    Endpoint externo para disparar logros manualmente.
    Protegido por SERVICE_API_KEY.
    Útil para logros huérfanos: fundador_2026, madrugador, etc.
    Body: {"user_id": int, "achievement_id": str}
    """
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    expected = current_app.config.get('SERVICE_API_KEY')
    if not expected or api_key != expected:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    achievement_id = data.get('achievement_id')
    event_data = data.get('event_data') or {}

    if not user_id or not achievement_id:
        return jsonify({'success': False, 'error': 'missing user_id or achievement_id'}), 400

    from app.services.achievement_engine import evaluate as eval_achievement
    from app.models import User

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'error': 'user_not_found'}), 404

    from app.services.achievement_definitions import VELZIA_ACHIEVEMENTS
    if achievement_id not in VELZIA_ACHIEVEMENTS:
        return jsonify({'success': False, 'error': 'unknown_achievement'}), 400

    # Fire the achievement via evaluate using a generic event type
    eval_achievement(user_id, 'manual_trigger', {**event_data, '_achievement_id': achievement_id})
    return jsonify({'success': True, 'message': f'Achievement {achievement_id} triggered'}), 200


@api_webhooks_bp.route('/rewards/generate', methods=['POST'])
def generate_reward():
    """
    Endpoint para que n8n genere recompensas sin duplicar lógica.
    Protegido por SERVICE_API_KEY.
    Body: {"plan": str, "user_id": int, "restaurant_id": int, "last_reward_label": str?}
    """
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    expected = current_app.config.get('SERVICE_API_KEY')
    if not expected or api_key != expected:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    plan = data.get('plan')
    user_id = data.get('user_id')
    restaurant_id = data.get('restaurant_id')
    last_reward_label = data.get('last_reward_label')

    if not plan or not user_id or not restaurant_id:
        return jsonify({'success': False, 'error': 'missing plan, user_id or restaurant_id'}), 400

    valid_plans = ('emprendedor', 'crecimiento', 'elite')
    if plan not in valid_plans:
        return jsonify({
            'success': False,
            'error': f'plan must be one of {valid_plans} (trial no recibe recompensas)'
        }), 400

    from app.services.reward_service import generate_reward as gen
    reward_data = gen(plan, last_reward_label)
    if not reward_data:
        return jsonify({'success': False, 'error': 'reward generation returned None'}), 500

    try:
        from app.models import RewardClaim
        claim = RewardClaim(
            user_id=user_id,
            restaurant_id=restaurant_id,
            short_code=reward_data['short_code'],
            token=reward_data['token'],
            plan_key=plan,
            rarity=reward_data['rarity'],
            reward_type=reward_data['type'],
            reward_value=reward_data.get('value'),
            reward_label=reward_data['label'],
            status='pending',
        )
        db.session.add(claim)
        db.session.commit()
        current_app.logger.info(
            'Reward generado: id=%d plan=%s rarity=%s type=%s para user=%d',
            claim.id, plan, reward_data['rarity'], reward_data['type'], user_id,
        )

        from app.services.reward_service import build_email_html
        user = db.session.get(User, user_id)
        email = user.email if user else ''
        claim_url = f"{current_app.config.get('BASE_URL', '')}/reclamar/{reward_data['short_code']}"

        return jsonify({
            'success': True,
            'data': {
                'id': claim.id,
                'short_code': reward_data['short_code'],
                'rarity': reward_data['rarity'],
                'emoji': reward_data['emoji'],
                'color': reward_data['color'],
                'type': reward_data['type'],
                'value': reward_data.get('value'),
                'label': reward_data['label'],
                'claim_url': claim_url,
                'email': email,
                'email_html': build_email_html(claim_url, reward_data['label']),
            },
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error('Error creating reward claim: %s', e)
        return jsonify({'success': False, 'error': 'reward_creation_failed'}), 500


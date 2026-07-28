import re
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, jsonify, abort, current_app, session, redirect, url_for
from app import db
from app.models import RewardClaim, AITokenWallet, AITokenTransaction, UserAchievement
from app.extensions import limiter
from app.utils.subscription import PLAN_LIMITS

rewards_bp = Blueprint('rewards', __name__, url_prefix='/reclamar')

SHORT_CODE_PATTERN = re.compile(r'^[A-Za-z0-9\-_]{22}$')
EXPIRATION_DAYS = 7


def _get_rarity_emoji(rarity: str) -> str:
    return {'common': '🎁', 'uncommon': '🌟', 'rare': '💎'}.get(rarity, '🎁')


def _get_rarity_label(rarity: str) -> str:
    return {'common': 'Común', 'uncommon': 'Poco Común', 'rare': '¡Muy Raro!'}.get(rarity, 'Común')


_MONTHS = {1:'enero',2:'febrero',3:'marzo',4:'abril',5:'mayo',6:'junio',
           7:'julio',8:'agosto',9:'septiembre',10:'octubre',11:'noviembre',12:'diciembre'}


def _sidebar_context(reward: RewardClaim) -> dict:
    restaurant = reward.restaurant
    month = restaurant.created_at.month if restaurant.created_at else 1
    year = restaurant.created_at.year if restaurant.created_at else 2026

    from app.services.streak_service import get_streak
    streak_info = get_streak(restaurant.id) if restaurant.id else {}

    return {
        'restaurant_name': restaurant.name,
        'plan_name': PLAN_LIMITS.get(restaurant.plan_type, {}).get('name', restaurant.plan_type.capitalize()),
        'cliente_desde': f'{_MONTHS[month]} {year}',
        'rewards_count': RewardClaim.query.filter_by(user_id=reward.user_id, status='claimed').count(),
        'achievements_count': UserAchievement.query.filter_by(user_id=reward.user_id).count(),
        'streak': streak_info,
    }


def _render_reward(reward: RewardClaim):
    ctx = _sidebar_context(reward)
    return render_template('rewards/claim.html',
        reward=reward,
        rarity_emoji=_get_rarity_emoji(reward.rarity),
        rarity_label=_get_rarity_label(reward.rarity),
        **ctx,
    )


def _check_expired(reward: RewardClaim) -> bool:
    if reward.status == 'expired':
        return True
    if reward.created_at and datetime.now(timezone.utc) - reward.created_at > timedelta(days=EXPIRATION_DAYS):
        if reward.status == 'pending':
            reward.status = 'expired'
            db.session.commit()
        return True
    return False


def _resolve_reward(short_code: str | None) -> RewardClaim | None:
    if short_code and SHORT_CODE_PATTERN.match(short_code):
        return RewardClaim.query.filter_by(short_code=short_code).first()
    token = request.args.get('token', '').strip()
    if token:
        return RewardClaim.query.filter_by(token=token).first()
    qs_code = request.args.get('short_code', '').strip()
    if qs_code and SHORT_CODE_PATTERN.match(qs_code):
        return RewardClaim.query.filter_by(short_code=qs_code).first()
    if short_code:
        return RewardClaim.query.filter_by(short_code=short_code).first()
    return None


@rewards_bp.route('/', methods=['GET'])
@rewards_bp.route('/<short_code>', methods=['GET'])
def claim_page(short_code=None):
    reward = _resolve_reward(short_code)

    # Sin short_code: intentar desde la sesión
    if not reward:
        rid = session.get('reward_id')
        if rid:
            reward = db.session.get(RewardClaim, rid)

    if not reward:
        return render_template('rewards/claim.html', error='Este enlace no es válido.'), 404

    session['reward_id'] = reward.id

    # Mostrar el reward en su estado actual (pendiente, reclamado o expirado)
    # sin redirigir a otro — cada short_code tiene su propio estado.
    if _check_expired(reward):
        return _render_reward(reward)

    return _render_reward(reward)


@rewards_bp.route('/claim', methods=['POST'])
@limiter.limit("5 per minute;20 per hour")
def claim_reward():
    reward_id = session.get('reward_id')
    if not reward_id:
        return jsonify({'success': False, 'error': 'Sesión inválida. Abre el enlace de nuevo.'}), 403

    origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
    allowed = current_app.config.get('BASE_URL', '')
    if allowed and origin and allowed not in origin:
        current_app.logger.warning('Recompensa: Origen no permitido %s', origin)
        return jsonify({'success': False, 'error': 'Origen no permitido'}), 403

    reward = RewardClaim.query.get(reward_id)
    if not reward:
        session.pop('reward_id', None)
        return jsonify({'success': False, 'error': 'Recompensa no encontrada'}), 404

    if reward.status == 'claimed':
        session.pop('reward_id', None)
        return jsonify({'success': False, 'error': 'Ya reclamaste este regalo'}), 409

    if _check_expired(reward):
        session.pop('reward_id', None)
        return jsonify({'success': False, 'error': 'Este regalo ha expirado'}), 410

    reward.status = 'claimed'
    reward.claimed_at = datetime.now(timezone.utc)
    reward.claimed_ip = request.remote_addr

    # ── Fulfillment: aplicar la recompensa ──
    from app.models import User, Restaurant, DiscountCoupon
    user = db.session.get(User, reward.user_id)
    fulfillment_error = None

    if user:
        try:
            if reward.reward_type == 'ai_tokens' and reward.reward_value:
                wallet = AITokenWallet.query.filter_by(user_id=user.id).first()
                if wallet:
                    AITokenWallet.query.filter_by(id=wallet.id).update(
                        {AITokenWallet.extra_tokens: AITokenWallet.extra_tokens + reward.reward_value}
                    )
                    tx = AITokenTransaction(
                        user_id=user.id, type='reward',
                        amount=reward.reward_value,
                        source='sorpresa_velzia',
                        description=f'Sorpresa Velzia: +{reward.reward_value} tokens ({reward.reward_label})',
                    )
                    db.session.add(tx)
                    current_app.logger.info(
                        'Reward %d: %d tokens acreditados a usuario %d',
                        reward.id, reward.reward_value, user.id,
                    )
                else:
                    fulfillment_error = 'wallet_not_found'

            elif reward.reward_type == 'free_month':
                restaurant = db.session.get(Restaurant, reward.restaurant_id)
                if restaurant:
                    now_utc = datetime.now(timezone.utc)
                    expires = restaurant.subscription_expires_at
                    if expires and expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if expires and expires > now_utc:
                        restaurant.subscription_expires_at = expires + timedelta(days=30)
                    else:
                        restaurant.subscription_expires_at = now_utc + timedelta(days=30)
                    current_app.logger.info(
                        'Reward %d: mes gratis aplicado a restaurante %d',
                        reward.id, restaurant.id,
                    )
                else:
                    fulfillment_error = 'restaurant_not_found'

            elif reward.reward_type == 'discount' and reward.reward_value:
                coupon = DiscountCoupon(
                    restaurant_id=reward.restaurant_id,
                    percentage=reward.reward_value,
                    status='pending',
                    reward_claim_id=reward.id,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=60),
                )
                db.session.add(coupon)
                current_app.logger.info(
                    'Reward %d: cupón %d%% creado (id=%d) para restaurante %d',
                    reward.id, reward.reward_value, coupon.id, reward.restaurant_id,
                )

            elif reward.reward_type in ('badge', 'early_access'):
                current_app.logger.info(
                    'Reward %d: %s "%s" — pendiente de UI',
                    reward.id, reward.reward_type, reward.reward_label,
                )

        except Exception as e:
            db.session.rollback()
            fulfillment_error = str(e)
            current_app.logger.error('Error fulfill reward %d: %s', reward.id, e)

    if not fulfillment_error:
        db.session.commit()

    session.pop('reward_id', None)

    from app.services.achievement_engine import evaluate as eval_achievement
    try:
        eval_achievement(reward.user_id, 'reward_claimed', {'rarity': reward.rarity})
    except Exception:
        current_app.logger.warning("Error evaluando logro por reward claim", exc_info=True)

    current_app.logger.info('Recompensa %d reclamada desde %s', reward.id, reward.claimed_ip)

    if fulfillment_error:
        return jsonify({
            'success': False,
            'error': 'fulfillment_error',
            'message': 'La recompensa se registró pero hubo un error al aplicarla. Contacta a soporte.',
        }), 500

    return jsonify({'success': True, 'message': '¡Recompensa reclamada con éxito!'})

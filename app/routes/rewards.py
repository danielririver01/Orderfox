import re
from uuid import UUID
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, jsonify, abort, current_app
from app import db
from app.models import RewardClaim
from app.extensions import limiter

rewards_bp = Blueprint('rewards', __name__, url_prefix='/reclamar')

UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.I)

EXPIRATION_DAYS = 7


def _is_valid_uuid(s: str) -> bool:
    return bool(UUID_PATTERN.match(s))


def _get_rarity_emoji(rarity: str) -> str:
    return {'common': '🎁', 'uncommon': '🌟', 'rare': '💎'}.get(rarity, '🎁')


def _get_rarity_label(rarity: str) -> str:
    return {'common': 'Común', 'uncommon': 'Poco Común', 'rare': '¡Muy Raro!'}.get(rarity, 'Común')


def _get_reward(reward: RewardClaim):
    return render_template('rewards/claim.html',
        reward=reward,
        rarity_emoji=_get_rarity_emoji(reward.rarity),
        rarity_label=_get_rarity_label(reward.rarity),
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


@rewards_bp.route('', methods=['GET'])
def claim_page():
    token = request.args.get('token', '').strip()
    if not token or not _is_valid_uuid(token):
        abort(404)

    reward = RewardClaim.query.filter_by(token=token).first()
    if not reward:
        return render_template('rewards/claim.html', error='Este enlace no es válido.'), 404

    if _check_expired(reward):
        return _get_reward(reward)

    return _get_reward(reward)


@rewards_bp.route('/claim', methods=['POST'])
@limiter.limit("5 per minute;20 per hour")
def claim_reward():
    origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
    allowed = current_app.config.get('BASE_URL', '')
    if allowed and origin and allowed not in origin:
        current_app.logger.warning('Recompensa: Origen no permitido %s', origin)
        return jsonify({'success': False, 'error': 'Origen no permitido'}), 403

    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token or not _is_valid_uuid(token):
        return jsonify({'success': False, 'error': 'Token inválido'}), 400

    reward = RewardClaim.query.filter_by(token=token).first()
    if not reward:
        return jsonify({'success': False, 'error': 'Recompensa no encontrada'}), 404

    if reward.status == 'claimed':
        return jsonify({'success': False, 'error': 'Ya reclamaste este regalo'}), 409

    if _check_expired(reward):
        return jsonify({'success': False, 'error': 'Este regalo ha expirado'}), 410

    reward.status = 'claimed'
    reward.claimed_at = datetime.now(timezone.utc)
    reward.claimed_ip = request.remote_addr
    db.session.commit()

    current_app.logger.info('Recompensa %d reclamada desde %s', reward.id, reward.claimed_ip)
    return jsonify({'success': True, 'message': '¡Recompensa reclamada con éxito!'})

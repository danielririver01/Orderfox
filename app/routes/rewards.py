"""
rewards.py — Sorpresa Velzia
Rutas para reclamar recompensas y ver historial.
"""
from flask import Blueprint, render_template, request, jsonify, abort
from app import db
from app.models import RewardClaim
from datetime import datetime, timezone

rewards_bp = Blueprint('rewards', __name__, url_prefix='/reclamar')


def _get_rarity_emoji(rarity: str) -> str:
    return {'common': '🎁', 'uncommon': '🌟', 'rare': '💎'}.get(rarity, '🎁')


def _get_rarity_color(rarity: str) -> str:
    return {'common': '#22c55e', 'uncommon': '#3b82f6', 'rare': '#a855f7'}.get(rarity, '#22c55e')


def _get_rarity_label(rarity: str) -> str:
    return {'common': 'Común', 'uncommon': 'Poco Común', 'rare': '¡Muy Raro!'}.get(rarity, 'Común')


@rewards_bp.route('', methods=['GET'])
def claim_page():
    token = request.args.get('token', '').strip()
    if not token:
        abort(404)

    reward = RewardClaim.query.filter_by(token=token).first()
    if not reward:
        return render_template('rewards/claim.html', error='Este enlace no es válido.'), 404

    if reward.status == 'claimed':
        return render_template('rewards/claim.html',
            error='Ya reclamaste este regalo',
            reward=reward,
            rarity_emoji=_get_rarity_emoji(reward.rarity),
            rarity_color=_get_rarity_color(reward.rarity),
            rarity_label=_get_rarity_label(reward.rarity),
        )

    if reward.status == 'expired':
        return render_template('rewards/claim.html',
            error='Este regalo ha expirado',
            reward=reward,
            rarity_emoji=_get_rarity_emoji(reward.rarity),
            rarity_color=_get_rarity_color(reward.rarity),
            rarity_label=_get_rarity_label(reward.rarity),
        )

    return render_template('rewards/claim.html',
        reward=reward,
        rarity_emoji=_get_rarity_emoji(reward.rarity),
        rarity_color=_get_rarity_color(reward.rarity),
        rarity_label=_get_rarity_label(reward.rarity),
    )


@rewards_bp.route('/claim', methods=['POST'])
def claim_reward():
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'success': False, 'error': 'Token requerido'}), 400

    reward = RewardClaim.query.filter_by(token=token).first()
    if not reward:
        return jsonify({'success': False, 'error': 'Recompensa no encontrada'}), 404

    if reward.status == 'claimed':
        return jsonify({'success': False, 'error': 'Ya reclamaste este regalo'}), 409

    if reward.status == 'expired':
        return jsonify({'success': False, 'error': 'Este regalo ha expirado'}), 410

    reward.status = 'claimed'
    reward.claimed_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'success': True, 'message': '¡Recompensa reclamada con éxito!'})

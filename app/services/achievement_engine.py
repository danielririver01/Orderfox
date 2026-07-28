from datetime import datetime, timezone
from flask import session, current_app
from app import db
from app.models import UserAchievement, RewardClaim
from app.services.achievement_definitions import VELZIA_ACHIEVEMENTS, RARITY_ORDER


def _unlock(user_id: int, achievement_id: str) -> UserAchievement | None:
    ach = VELZIA_ACHIEVEMENTS.get(achievement_id)
    if not ach:
        return None

    existing = UserAchievement.query.filter_by(
        user_id=user_id, achievement_id=achievement_id
    ).first()
    if existing:
        return None

    record = UserAchievement(
        user_id=user_id,
        achievement_id=achievement_id,
        current_progress=ach.get('required_progress', 1),
        required_progress=ach.get('required_progress', 1),
        earned_at=datetime.now(timezone.utc),
    )
    db.session.add(record)
    db.session.commit()

    if ach.get('reward_tokens'):
        _credit_tokens(user_id, ach['reward_tokens'])

    try:
        session['_new_achievement'] = achievement_id
    except RuntimeError:
        pass

    current_app.logger.info(
        'Logro %s desbloqueado para usuario %d (+%s tokens)',
        achievement_id, user_id, ach.get('reward_tokens', 0),
    )
    return record


def _credit_tokens(user_id: int, amount: int):
    from app.models import AITokenTransaction, User
    user = User.query.get(user_id)
    if not user:
        return
    user.ai_tokens = (user.ai_tokens or 0) + amount
    tx = AITokenTransaction(
        user_id=user_id,
        type='achievement',
        amount=amount,
        description=f'Logro desbloqueado: +{amount} tokens',
    )
    db.session.add(tx)


def evaluate(user_id: int, event_type: str, event_data: dict = None):
    event_data = event_data or {}

    if event_type == 'subscription_activated':
        _unlock(user_id, 'primer_pago')

    elif event_type == 'subscription_renewed':
        months = event_data.get('months_active', 0)
        if months >= 12:
            _unlock(user_id, 'un_ano')
        if months >= 6:
            _unlock(user_id, 'seis_meses')
        if months >= 3:
            _unlock(user_id, 'tres_meses')

    elif event_type == 'ai_analysis':
        total = event_data.get('total_analyses', 0)
        if total >= 100:
            _unlock(user_id, 'cien_analisis')
        if total >= 50:
            _unlock(user_id, 'cincuenta_analisis')
        if total >= 10:
            _unlock(user_id, 'diez_analisis')
        _unlock(user_id, 'primer_analisis')

    elif event_type == 'manual_trigger':
        ach_id = event_data.get('_achievement_id')
        if ach_id:
            _unlock(user_id, ach_id)

    elif event_type == 'reward_claimed':
        rarity = event_data.get('rarity', '')
        _unlock(user_id, 'primer_sorpresa')

        rarity_map = {'common': 'coleccionista_1', 'uncommon': 'coleccionista_2', 'rare': 'coleccionista_3'}
        if rarity in rarity_map:
            _unlock(user_id, rarity_map[rarity])

        total_claimed = RewardClaim.query.filter(
            RewardClaim.user_id == user_id,
            RewardClaim.status == 'claimed',
        ).count()
        if total_claimed >= 3:
            _unlock(user_id, 'tocador_sorpresa')

        earned_rarities = set()
        for r_id in ['coleccionista_1', 'coleccionista_2', 'coleccionista_3']:
            if UserAchievement.query.filter_by(user_id=user_id, achievement_id=r_id).first():
                earned_rarities.add(r_id)
        if len(earned_rarities) >= 3:
            _unlock(user_id, 'coleccionista_total')


def get_profile(user_id: int) -> dict:
    earned = {
        a.achievement_id: a
        for a in UserAchievement.query.filter_by(user_id=user_id).all()
    }

    achievements = []
    for ach_id, ach in VELZIA_ACHIEVEMENTS.items():
        entry = dict(ach)
        entry['earned'] = ach_id in earned
        if entry['earned']:
            entry['earned_at'] = earned[ach_id].earned_at
        if entry.get('required_progress'):
            entry['current_progress'] = earned[ach_id].current_progress if entry['earned'] else 0
            entry['required_progress'] = ach['required_progress']
        else:
            entry['current_progress'] = 1 if entry['earned'] else 0
            entry['required_progress'] = 1
        achievements.append(entry)

    achievements.sort(key=lambda a: (
        not a['earned'],
        RARITY_ORDER.get(a.get('rarity', 'common'), 0)
    ))

    total = len(achievements)
    unlocked = sum(1 for a in achievements if a['earned'])

    return {
        'achievements': achievements,
        'total': total,
        'unlocked': unlocked,
        'categories': _categorize(achievements),
    }


def _categorize(achievements: list) -> dict:
    from app.services.achievement_definitions import CATEGORIES
    cats = {}
    for cat_id, cat_info in CATEGORIES.items():
        items = [a for a in achievements if a.get('category') == cat_id]
        unlocked = sum(1 for a in items if a['earned'])
        visible = [a for a in items if a['earned'] or not a.get('secret', False)]
        cats[cat_id] = {
            **cat_info,
            'achievement_list': items,
            'total': len(items),
            'unlocked': unlocked,
            'visible_count': len(visible),
        }
    return cats

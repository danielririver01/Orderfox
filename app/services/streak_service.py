from datetime import datetime, timezone
from app import db
from app.models import Streak, Restaurant

TIER_THRESHOLDS = [0, 1, 3, 6, 12]
TIER_NAMES = {0: None, 1: 'Bronce', 2: 'Plata', 3: 'Oro', 4: 'Diamante'}
TIER_ICON = {0: '', 1: '🥉', 2: '🥈', 3: '🥇', 4: '💎'}


def calculate_tier(renewal_count: int) -> int:
    for i, threshold in enumerate(reversed(TIER_THRESHOLDS)):
        if renewal_count >= threshold:
            return len(TIER_THRESHOLDS) - 1 - i
    return 0


def _tier_name(tier: int) -> str | None:
    return TIER_NAMES.get(tier)


def _tier_icon(tier: int) -> str:
    return TIER_ICON.get(tier, '')


def _days_remaining(restaurant: Restaurant, streak: Streak) -> tuple[int, int, int]:
    if not restaurant.subscription_expires_at:
        return 0, 0, 0
    expires = restaurant.subscription_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds_remaining = max(0, (expires - now).total_seconds())
    days_remaining = int(seconds_remaining // 86400) + (1 if seconds_remaining % 86400 > 0 else 0)
    cycle_start = streak.last_renewal_at or restaurant.created_at or now
    if cycle_start.tzinfo is None:
        cycle_start = cycle_start.replace(tzinfo=timezone.utc)
    total_cycle_seconds = max(1, (expires - cycle_start).total_seconds())
    total = max(1, int(total_cycle_seconds // 86400) + (1 if total_cycle_seconds % 86400 > 0 else 0))
    progress = int((1 - days_remaining / total) * 100)
    return days_remaining, total, progress


def get_streak(restaurant_id: int) -> dict:
    restaurant = db.session.get(Restaurant, restaurant_id)
    if not restaurant:
        return {'tier': 0, 'tier_name': None, 'icon': '', 'status': 'no_restaurant', 'days_remaining': 0, 'days_in_cycle': 0, 'progress_pct': 0}

    streak = Streak.query.filter_by(restaurant_id=restaurant_id).first()
    if not streak or not streak.renewal_count:
        return {'tier': 0, 'tier_name': None, 'icon': '', 'renewal_count': 0, 'highest_tier': 0, 'highest_tier_name': None, 'days_remaining': 0, 'days_in_cycle': 0, 'progress_pct': 0, 'status': 'inactive'}

    tier = calculate_tier(streak.renewal_count)
    days_remaining, days_in_cycle, progress = _days_remaining(restaurant, streak)

    def _build(extra=None):
        d = {
            'tier': tier,
            'tier_name': _tier_name(tier),
            'icon': _tier_icon(tier),
            'highest_tier': streak.highest_tier or 0,
            'highest_tier_name': _tier_name(streak.highest_tier or 0),
            'renewal_count': streak.renewal_count,
            'days_remaining': days_remaining if not extra else 0,
            'days_in_cycle': days_in_cycle,
            'progress_pct': progress,
            'status': extra or 'active',
        }
        return d

    if days_remaining == 0 and restaurant.subscription_expires_at:
        if restaurant.subscription_expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return _build('expired')

    return _build('active')


def bump_streak(restaurant_id: int, payment_id: str) -> dict:
    streak = Streak.query.filter_by(restaurant_id=restaurant_id).with_for_update().first()
    if not streak:
        streak = Streak(restaurant_id=restaurant_id)
        db.session.add(streak)

    if streak.last_payment_id == payment_id:
        return {'duplicate': True, 'tier': calculate_tier(streak.renewal_count or 0)}

    prev_renewal_count = streak.renewal_count or 0
    prev_tier = calculate_tier(prev_renewal_count)

    streak.renewal_count = prev_renewal_count + 1
    streak.last_renewal_at = datetime.now(timezone.utc)
    streak.last_payment_id = payment_id

    new_tier = calculate_tier(streak.renewal_count)
    streak.highest_tier = max(streak.highest_tier or 0, new_tier)

    db.session.commit()

    return {
        'duplicate': False,
        'prev_renewal_count': prev_renewal_count,
        'prev_tier': prev_tier,
        'new_renewal_count': streak.renewal_count,
        'new_tier': new_tier,
        'tier_changed': prev_tier != new_tier,
        'bonus_tier': new_tier if new_tier >= 1 else None,
    }


def reset_streak(restaurant_id: int) -> None:
    streak = Streak.query.filter_by(restaurant_id=restaurant_id).first()
    if not streak:
        return

    streak.renewal_count = 0
    streak.last_renewal_at = None
    db.session.commit()

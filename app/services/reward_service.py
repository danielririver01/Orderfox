"""
reward_service.py — Sorpresa Velzia
Reglas de recompensa 70/25/5 por plan, sin repetición consecutiva.
"""
import random
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

PlanKey = Literal['emprendedor', 'crecimiento', 'elite', 'trial']

REWARD_POOL: dict[PlanKey, dict[str, list[dict]]] = {
    'trial': {
        'common': [
            {'type': 'badge', 'value': 'trial_explorer', 'label': 'Insignia Explorador Velzia'},
            {'type': 'badge', 'value': 'trial_pioneer', 'label': 'Insignia Pionero'},
            {'type': 'badge', 'value': 'trial_taster', 'label': 'Insignia Catador'},
        ],
    },
    'emprendedor': {
        'common': [
            {'type': 'ai_tokens', 'value': 10, 'label': '10 tokens IA'},
            {'type': 'badge', 'value': 'early_adopter', 'label': 'Insignia Primeros Usuarios'},
            {'type': 'badge', 'value': 'collector_1', 'label': 'Insignia Coleccionista Bronce'},
        ],
        'uncommon': [
            {'type': 'discount', 'value': 15, 'label': '15% dto. próximo mes'},
            {'type': 'ai_tokens', 'value': 25, 'label': '25 tokens IA extra'},
            {'type': 'ai_tokens', 'value': 50, 'label': '50 tokens IA'},
        ],
        'rare': [
            {'type': 'free_month', 'label': '1 mes gratis (máx 1 vez cada 6 meses)'},
            {'type': 'ai_tokens', 'value': 100, 'label': '100 tokens IA'},
            {'type': 'discount', 'value': 30, 'label': '30% dto. próximo mes'},
        ],
    },
    'crecimiento': {
        'common': [
            {'type': 'ai_tokens', 'value': 15, 'label': '15 tokens IA'},
            {'type': 'ai_tokens', 'value': 20, 'label': '20 tokens IA'},
            {'type': 'badge', 'value': 'collector_2', 'label': 'Insignia Coleccionista Plata'},
        ],
        'uncommon': [
            {'type': 'discount', 'value': 15, 'label': '15% dto. próximo mes'},
            {'type': 'ai_tokens', 'value': 50, 'label': '50 tokens IA extra'},
            {'type': 'ai_tokens', 'value': 75, 'label': '75 tokens IA'},
        ],
        'rare': [
            {'type': 'free_month', 'label': '1 mes gratis (máx 1 vez cada 6 meses)'},
            {'type': 'ai_tokens', 'value': 150, 'label': '150 tokens IA'},
            {'type': 'discount', 'value': 25, 'label': '25% dto. próximo mes'},
        ],
    },
    'elite': {
        'common': [
            {'type': 'ai_tokens', 'value': 25, 'label': '25 tokens IA'},
            {'type': 'ai_tokens', 'value': 50, 'label': '50 tokens IA'},
            {'type': 'badge', 'value': 'collector_3', 'label': 'Insignia Coleccionista Oro'},
        ],
        'uncommon': [
            {'type': 'discount', 'value': 10, 'label': '10% dto. próximo mes'},
            {'type': 'ai_tokens', 'value': 100, 'label': '100 tokens IA extra'},
            {'type': 'ai_tokens', 'value': 200, 'label': '200 tokens IA'},
        ],
        'rare': [
            {'type': 'early_access', 'label': 'Acceso anticipado a nuevas funciones'},
            {'type': 'ai_tokens', 'value': 500, 'label': '500 tokens IA'},
            {'type': 'discount', 'value': 20, 'label': '20% dto. próximo mes'},
        ],
    },
}

STREAK_BONUS_BY_TIER = {
    1: [
        {'type': 'ai_tokens', 'value': 10, 'label': '10 tokens IA \u2022 Fidelidad Bronce'},
    ],
    2: [
        {'type': 'discount', 'value': 15, 'label': '15% dto. \u2022 Fidelidad Plata'},
        {'type': 'ai_tokens', 'value': 40, 'label': '40 tokens IA \u2022 Fidelidad Plata'},
    ],
    3: [
        {'type': 'free_month', 'label': '1 mes gratis \u2022 Fidelidad Oro'},
        {'type': 'ai_tokens', 'value': 75, 'label': '75 tokens IA \u2022 Fidelidad Oro'},
    ],
    4: [
        {'type': 'ai_tokens', 'value': 150, 'label': '150 tokens IA \u2022 Fidelidad Diamante'},
    ],
}


def get_bonus_pool(tier: int) -> list:
    return STREAK_BONUS_BY_TIER.get(tier, [])


def generate_streak_reward(tier: int) -> dict | None:
    pool = get_bonus_pool(tier)
    if not pool:
        return None
    reward = random.choice(pool)
    return {
        'rarity': 'uncommon' if tier <= 2 else 'rare',
        'emoji': RARITY_EMOJIS['uncommon' if tier <= 2 else 'rare'],
        'color': RARITY_COLORS['uncommon' if tier <= 2 else 'rare'],
        'type': reward['type'],
        'value': reward.get('value'),
        'label': reward['label'],
        'is_streak_bonus': True,
    }


RARITY_ROLLS: dict[str, float] = {
    'common': 0.70,
    'uncommon': 0.25,
    'rare': 0.05,
}

RARITY_EMOJIS: dict[str, str] = {
    'common': '🎁',
    'uncommon': '🌟',
    'rare': '💎',
}

RARITY_COLORS: dict[str, str] = {
    'common': '#22c55e',
    'uncommon': '#3b82f6',
    'rare': '#a855f7',
}


def _roll_rarity() -> str:
    roll = random.random()
    cumulative = 0.0
    for rarity, chance in RARITY_ROLLS.items():
        cumulative += chance
        if roll < cumulative:
            return rarity
    return 'common'


def _pick_reward(plan: str, rarity: str, last_reward_type: Optional[str] = None) -> dict:
    pool = REWARD_POOL.get(plan, REWARD_POOL['emprendedor'])
    candidates = pool.get(rarity, pool['common'])

    if last_reward_type and len(candidates) > 1:
        filtered = [r for r in candidates if r['label'] != last_reward_type]
        if filtered:
            candidates = filtered

    return random.choice(candidates)


def generate_reward(
    plan: PlanKey,
    last_reward_label: Optional[str] = None,
    force_rarity: Optional[str] = None,
) -> dict | None:
    if plan == 'trial':
        rarity = 'common'
    else:
        rarity = force_rarity or _roll_rarity()
    reward = _pick_reward(plan, rarity, last_reward_label)
    raw_value = reward.get('value')
    value = raw_value if isinstance(raw_value, (int, float)) else None

    return {
        'rarity': rarity,
        'emoji': RARITY_EMOJIS[rarity],
        'color': RARITY_COLORS[rarity],
        'type': reward['type'],
        'value': value,
        'label': reward['label'],
        'token': str(uuid.uuid4()),
        'short_code': secrets.token_urlsafe(16),
        'created_at': datetime.now(timezone.utc).isoformat(),
    }


def can_receive_free_month(
    user_id: int,
    last_free_month_date: Optional[datetime] = None,
) -> bool:
    if last_free_month_date is None:
        return True
    six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
    return last_free_month_date < six_months_ago


def apply_reward_protocol(reward: dict) -> str:
    emoji_map = {
        'ai_tokens': '🤖',
        'discount': '💰',
        'free_month': '🎉',
        'badge': '🏅',
        'early_access': '🚀',
    }
    return emoji_map.get(reward['type'], '🎁')


def build_email_html(claim_url: str, reward_label: str) -> str:
    from flask import render_template
    return render_template('rewards/email_congratulations.html', claim_url=claim_url, reward_label=reward_label)

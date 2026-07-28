"""
Modelos del sistema de recompensas, logros, streaks y cupones de descuento.
"""

from datetime import datetime, timezone
from app.models import db, AwareDateTime


class PreRegistration(db.Model):
    __tablename__ = 'pre_registrations'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    selected_plan = db.Column(db.String(20), nullable=False, default='trial')
    whatsapp_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<PreRegistration {self.email} - {self.selected_plan}>'


class TrialHistory(db.Model):
    __tablename__ = 'trial_history'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=True)
    whatsapp_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<TrialHistory {self.email} - {self.whatsapp_phone}>'


class Expense(db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50), default='otros')
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    restaurant = db.relationship('Restaurant', backref=db.backref('expenses', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Expense {self.description} ${self.amount}>'


class RewardClaim(db.Model):
    """Recompensa generada tras pago (Sorpresa Velzia)."""
    __tablename__ = 'reward_claims'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    short_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    plan_key = db.Column(db.String(50), nullable=False)
    rarity = db.Column(db.String(20), nullable=False)
    reward_type = db.Column(db.String(50), nullable=False)
    reward_value = db.Column(db.Integer, nullable=True)
    reward_label = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    claimed_at = db.Column(AwareDateTime, nullable=True)
    claimed_ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('reward_claims', lazy='dynamic', cascade='all, delete-orphan'))
    restaurant = db.relationship('Restaurant', backref=db.backref('reward_claims', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<RewardClaim {self.id} {self.rarity}/{self.reward_type} for user {self.user_id}>'


class UserAchievement(db.Model):
    """Logro de un usuario dentro del sistema de Logros Velzia."""
    __tablename__ = 'user_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    achievement_id = db.Column(db.String(50), nullable=False, index=True)
    current_progress = db.Column(db.Integer, default=1, nullable=False)
    required_progress = db.Column(db.Integer, default=1, nullable=False)
    earned_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('achievements', lazy='dynamic', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )

    def __repr__(self):
        return f'<UserAchievement {self.achievement_id} for user {self.user_id}>'


class Streak(db.Model):
    __tablename__ = 'streaks'
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(
        db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'),
        unique=True, nullable=False, index=True,
    )
    renewal_count = db.Column(db.Integer, default=0, nullable=False)
    highest_tier = db.Column(db.Integer, default=0, nullable=False)
    last_renewal_at = db.Column(AwareDateTime, nullable=True)
    last_payment_id = db.Column(db.String(50), nullable=True)

    restaurant = db.relationship('Restaurant', backref=db.backref('streak', uselist=False, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Streak r#{self.restaurant_id} count={self.renewal_count}>'


class DiscountCoupon(db.Model):
    """Cupón de descuento generado al reclamar un reward tipo discount."""
    __tablename__ = 'discount_coupons'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False, index=True)
    percentage = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    reward_claim_id = db.Column(db.Integer, db.ForeignKey('reward_claims.id', ondelete='SET NULL'), nullable=True)
    preference_id = db.Column(db.String(100), nullable=True)
    applied_to_payment_id = db.Column(db.String(50), nullable=True)
    reserved_at = db.Column(AwareDateTime, nullable=True)
    applied_at = db.Column(AwareDateTime, nullable=True)
    expires_at = db.Column(AwareDateTime, nullable=False)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    restaurant = db.relationship('Restaurant', backref=db.backref('discount_coupons', lazy='dynamic', cascade='all, delete-orphan'))
    reward_claim = db.relationship('RewardClaim', backref=db.backref('discount_coupon', uselist=False))

    def __repr__(self):
        return f'<DiscountCoupon {self.id} r#{self.restaurant_id} {self.percentage}% {self.status}>'

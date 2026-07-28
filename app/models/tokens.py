"""
Modelos del sistema de tokens IA (wallet + transacciones).
"""

from datetime import datetime, timezone
from app.models import db, AwareDateTime


class AITokenWallet(db.Model):
    """
    Billetera de tokens IA por usuario. Una fila por usuario.

    Regla "Fair Play":
    - plan_tokens: asignados por el plan mensual. Se resetean al renovar.
      Si es NULL → plan Elite (ilimitado), nunca se descuenta.
    - extra_tokens: comprados con top-up (MP). Se acumulan, no expiran.
    - El consumo descuenta primero plan_tokens, luego extra_tokens.
    """
    __tablename__ = 'ai_token_wallets'

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                               nullable=False, unique=True)
    # NULL = Elite (ilimitado). MySQL no soporta Infinity en INT.
    plan_limit     = db.Column(db.Integer, nullable=True)
    plan_tokens    = db.Column(db.Integer, nullable=False, default=0)   # restantes del mes
    extra_tokens   = db.Column(db.Integer, nullable=False, default=0)   # comprados, sin expirar
    tokens_used_month = db.Column(db.Integer, nullable=False, default=0) # contador mensual
    reset_at       = db.Column(AwareDateTime, nullable=True)             # próx. reset
    created_at     = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = db.Column(AwareDateTime,
                               default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('token_wallet', uselist=False,
                                                       cascade='all, delete-orphan'))

    @property
    def is_elite(self):
        """Plan Elite = 3000 tokens (basado en plan_type del restaurant)."""
        return self.user.restaurant.plan_type == 'elite' if self.user.restaurant else False

    @property
    def total_available(self):
        """Tokens disponibles para usar ahora mismo."""
        return self.plan_tokens + self.extra_tokens

    @property
    def usage_percent(self):
        """Porcentaje de uso del plan mensual (0-100). None si no hay límite."""
        if not self.plan_limit:
            return None
        used = self.plan_limit - self.plan_tokens
        return round((used / self.plan_limit) * 100, 1)

    def can_scan(self):
        """¿El usuario puede hacer un escaneo ahora?"""
        return self.total_available > 0

    def __repr__(self):
        return (f'<AITokenWallet user={self.user_id} '
                f'plan={self.plan_tokens}/{self.plan_limit} extra={self.extra_tokens}>')


class AITokenTransaction(db.Model):
    """
    Log inmutable de cada operación de tokens.
    amount > 0 = recarga. amount < 0 = consumo.
    """
    __tablename__ = 'ai_token_transactions'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                              nullable=False)
    # Tipos: 'consume', 'topup_plan', 'topup_purchase', 'elite_scan'
    type          = db.Column(db.String(20), nullable=False)
    amount        = db.Column(db.Integer, nullable=False)  # +recarga / -consumo
    # Fuente: 'scanner_ia', 'plan_renewal', 'mp_purchase', 'migration_seed'
    source        = db.Column(db.String(50), nullable=False)
    mp_payment_id = db.Column(db.String(100), nullable=True, unique=True)
    description   = db.Column(db.String(200), nullable=True)
    created_at    = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('token_transactions', lazy='dynamic',
                                                       cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<AITokenTransaction user={self.user_id} type={self.type} amount={self.amount}>'

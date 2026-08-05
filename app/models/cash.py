"""
Modelo del Centro de Caja: cierres de caja persistentes.

Cada fila es un "cierre de caja": un snapshot de las ventas (basadas en
`paid_at`) dentro de un rango de tiempo [period_start, period_end) de un
restaurante, junto con el desglose por método de pago y el vuelto entregado.

Reglas de negocio (ver CashRegisterService):
- Un rango NO puede solaparse con otro cierre del mismo restaurante.
- `period_start` es único por restaurante (red de seguridad anti-doble cierre).
- `closed_by` queda registrado para soportar roles (cajero/admin) en el futuro;
  hoy todos los usuarios del restaurante pueden cerrar caja.
"""

from datetime import datetime, timezone
from app.models import db, AwareDateTime


class CashRegister(db.Model):
    __tablename__ = 'cash_registers'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    # Quién cerró la caja. NULL = sistema/tarea (no aplica hoy). FK a users.id.
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    period_start = db.Column(AwareDateTime, nullable=False)  # inicio del rango (UTC, exclusivo)
    period_end = db.Column(AwareDateTime, nullable=False)    # fin del rango (UTC, exclusivo)

    # Snapshot del periodo (basado en paid_at)
    total_sales = db.Column(db.Integer, default=0, nullable=False)
    total_orders = db.Column(db.Integer, default=0, nullable=False)
    avg_ticket = db.Column(db.Integer, default=0, nullable=False)

    # Desglose por método de pago
    cash_total = db.Column(db.Integer, default=0, nullable=False)
    cash_orders = db.Column(db.Integer, default=0, nullable=False)
    nequi_total = db.Column(db.Integer, default=0, nullable=False)
    nequi_orders = db.Column(db.Integer, default=0, nullable=False)
    bancolombia_total = db.Column(db.Integer, default=0, nullable=False)
    bancolombia_orders = db.Column(db.Integer, default=0, nullable=False)
    card_total = db.Column(db.Integer, default=0, nullable=False)
    card_orders = db.Column(db.Integer, default=0, nullable=False)

    # Suma del vuelto entregado en efectivo (para cuadre físico de caja)
    cash_change_total = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'period_start', name='uq_restaurant_period_start'),
    )

    restaurant = db.relationship('Restaurant', backref=db.backref(
        'cash_registers', lazy=True, cascade='all, delete-orphan'))
    closed_by_user = db.relationship('User', backref=db.backref(
        'cash_registers_closed', lazy=True), foreign_keys=[closed_by])

    def __repr__(self):
        return f'<CashRegister {self.id} restaurant={self.restaurant_id} {self.period_start}–{self.period_end}>'

    @property
    def method_breakdown(self):
        """Desglose por método de pago como dict ordenado (para la vista/print)."""
        return [
            {'key': 'cash', 'label': 'Efectivo', 'total': self.cash_total, 'orders': self.cash_orders},
            {'key': 'nequi', 'label': 'Nequi', 'total': self.nequi_total, 'orders': self.nequi_orders},
            {'key': 'bancolombia', 'label': 'Bancolombia', 'total': self.bancolombia_total, 'orders': self.bancolombia_orders},
            {'key': 'card', 'label': 'Tarjeta', 'total': self.card_total, 'orders': self.card_orders},
        ]

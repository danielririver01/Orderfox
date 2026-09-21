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


class CashShift(db.Model):
    """Turno de caja: apertura con fondo inicial y cierre con conteo físico.

    - Un solo turno `open` por restaurante (validado en servicio; el unique
      parcial no es portable a SQLite, así que la regla vive en
      `CashShiftService.open_shift` + chequeo en `_apply_payment`).
    - `expected_cash` = fondo inicial + ventas netas en efectivo desde
      `opened_at` (totales menos vuelto `change_due`).
    - `difference` = contado - esperado (negativo = faltante).
    """

    __tablename__ = 'cash_shifts'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    status = db.Column(db.String(10), default='open', nullable=False, server_default='open')

    opening_amount = db.Column(db.Integer, default=0, nullable=False)
    opened_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    opened_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    closed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    closed_at = db.Column(AwareDateTime, nullable=True)

    expected_cash = db.Column(db.Integer, nullable=True)
    counted_cash = db.Column(db.Integer, nullable=True)
    difference = db.Column(db.Integer, nullable=True)

    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_cash_shifts_restaurant_status', 'restaurant_id', 'status'),
    )

    restaurant = db.relationship('Restaurant', backref=db.backref(
        'cash_shifts', lazy=True, cascade='all, delete-orphan'))
    opened_by_user = db.relationship('User', backref=db.backref(
        'cash_shifts_opened', lazy=True), foreign_keys=[opened_by])
    closed_by_user = db.relationship('User', backref=db.backref(
        'cash_shifts_closed', lazy=True), foreign_keys=[closed_by])

    def __repr__(self):
        return f'<CashShift {self.id} restaurant={self.restaurant_id} {self.status}>'


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

    # Arqueo opcional (modo estricto `Restaurant.require_cash_shift`):
    # fondo inicial del turno, esperado/contado/diferencia y turno origen.
    opening_amount = db.Column(db.Integer, default=0, nullable=False)
    expected_cash = db.Column(db.Integer, nullable=True)
    counted_cash = db.Column(db.Integer, nullable=True)
    difference = db.Column(db.Integer, nullable=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('cash_shifts.id', ondelete='SET NULL'),
                         nullable=True)

    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'period_start', name='uq_restaurant_period_start'),
    )

    restaurant = db.relationship('Restaurant', backref=db.backref(
        'cash_registers', lazy=True, cascade='all, delete-orphan'))
    closed_by_user = db.relationship('User', backref=db.backref(
        'cash_registers_closed', lazy=True), foreign_keys=[closed_by])
    shift = db.relationship('CashShift', backref=db.backref(
        'cash_registers', lazy=True))

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

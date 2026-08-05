"""
Modelos del dominio de pedidos (orders).
"""

from datetime import datetime, timezone
from app.models import db, AwareDateTime


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id', ondelete='SET NULL'), nullable=True)
    order_number = db.Column(db.String(20), nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending', nullable=False)
    total = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    # Pago (modal caja registradora). NULL = sin pago registrado aun.
    payment_method = db.Column(db.String(20), nullable=True)  # cash | nequi | bancolombia | card
    amount_received = db.Column(db.Integer, nullable=True)    # solo efectivo: lo que entregó el cliente
    change_due = db.Column(db.Integer, nullable=True)         # solo efectivo: vuelto a devolver
    paid_at = db.Column(AwareDateTime, nullable=True)         # cuándo se registró el pago
    # IP del cliente para rate limiting (P4)
    ip_address = db.Column(db.String(45), nullable=True, index=True)
    # Fecha de expiración para pedidos pendientes
    expires_at = db.Column(AwareDateTime, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relación con Restaurant y Table
    restaurant = db.relationship('Restaurant', backref=db.backref('orders', lazy=True, cascade='all, delete-orphan'))
    table = db.relationship('Table', backref=db.backref('orders', lazy=True))  # Sin cascade delete para preservar historial

    def __repr__(self):
        return f'<Order {self.order_number}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=True)
    product_name = db.Column(db.String(100), nullable=False)
    product_price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    modifiers_snapshot = db.Column(db.Text)
    subtotal = db.Column(db.Integer, nullable=False)

    # Relación con Order
    order = db.relationship('Order', backref=db.backref('items', lazy=True, cascade='all, delete-orphan'))
    restaurant = db.relationship('Restaurant', backref=db.backref('order_items', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<OrderItem {self.product_name} x{self.quantity}>'


class OrderCounter(db.Model):
    """Atomic counter for order numbers per restaurant per day (P5)."""
    __tablename__ = 'order_counters'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    counter = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint('restaurant_id', 'date', name='uq_restaurant_date'),)

    restaurant = db.relationship('Restaurant', backref=db.backref('order_counters', lazy=True,
                                                                   cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<OrderCounter restaurant={self.restaurant_id} date={self.date} count={self.counter}>'

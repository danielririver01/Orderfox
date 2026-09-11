"""
Modelos del dominio de reservas (mesas y reservaciones).

Convención de tiempo (v1.5):
- `reservation_date` y `reservation_time` se guardan en HORA LOCAL DE
  COLOMBIA (naive). Una reserva de "8pm" significa 8pm en Bogotá siempre:
  convertirla a UTC movería la fecha (8pm CO == 01:00 UTC del día siguiente)
  y rompería el calendario diario y el cálculo de disponibilidad. Colombia
  no usa horario de verano (ver app/utils/timezone.py).
- `created_at`, `confirmed_at`, `rejected_at` son columnas de auditoría y
  sí usan AwareDateTime en UTC (regla general del proyecto).
"""
from datetime import datetime, timezone

from app.models import AwareDateTime, db


class Reservation(db.Model):
    __tablename__ = 'reservations'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    # SET NULL: si se elimina la mesa, la reserva sobrevive (historial).
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id', ondelete='SET NULL'), nullable=True)

    # Datos del cliente
    customer_name = db.Column(db.String(100), nullable=False)
    customer_whatsapp = db.Column(db.String(20), nullable=False)
    customer_note = db.Column(db.Text, nullable=True)

    # Fecha y hora de la reserva (hora local Colombia — ver docstring del módulo)
    reservation_date = db.Column(db.Date, nullable=False, index=True)
    reservation_time = db.Column(db.Time, nullable=False)
    party_size = db.Column(db.Integer, nullable=False)

    # pendiente | confirmada | rechazada | completada | no_show
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)
    rejection_reason = db.Column(db.Text, nullable=True)

    # Recordatorio automático (APScheduler): True = ya se envió
    reminder_sent = db.Column(db.Boolean, default=False, nullable=False)

    # IP del cliente para rate limiting (mismo patrón que Order.ip_address)
    ip_address = db.Column(db.String(45), nullable=True, index=True)

    # Auditoría (UTC)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = db.Column(AwareDateTime, nullable=True)
    rejected_at = db.Column(AwareDateTime, nullable=True)

    restaurant = db.relationship('Restaurant',
                                 backref=db.backref('reservations', lazy=True,
                                                    cascade='all, delete-orphan'))
    # Sin cascade para preservar el historial si la mesa se elimina (patrón Order.table)
    table = db.relationship('Table', backref=db.backref('reservations', lazy=True))

    def __repr__(self):
        return f'<Reservation {self.id} {self.reservation_date} {self.reservation_time} {self.status}>'


class ReservationSettings(db.Model):
    """Configuración de reservas por restaurante (una fila por restaurante).

    La disponibilidad es matemática y configurable:
        fin de reserva = hora + service_duration_min + cleanup_buffer_min
    Una mesa queda bloqueada desde el inicio de la reserva hasta ese fin.
    """
    __tablename__ = 'reservation_settings'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'),
                              nullable=False, unique=True)

    service_duration_min = db.Column(db.Integer, default=90, nullable=False)
    cleanup_buffer_min = db.Column(db.Integer, default=15, nullable=False)
    min_notice_hours = db.Column(db.Integer, default=2, nullable=False)
    max_advance_days = db.Column(db.Integer, default=30, nullable=False)
    reservations_enabled = db.Column(db.Boolean, default=True, nullable=False)

    # Recordatorio automático (se envía al canal ntfy del restaurante)
    reminder_enabled = db.Column(db.Boolean, default=True, nullable=False)
    reminder_hours_before = db.Column(db.Integer, default=2, nullable=False)

    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    restaurant = db.relationship(
        'Restaurant',
        backref=db.backref('reservation_settings', lazy=True,
                           cascade='all, delete-orphan', uselist=False))

    def __repr__(self):
        return f'<ReservationSettings restaurant={self.restaurant_id}>'

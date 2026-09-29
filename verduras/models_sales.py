"""
Models de ventas del vertical Verduras (Semana 2).

⚠️ Mismo contrato que verduras/models.py: toda FK apunta a `businesses.id`
o a tablas propias `verduras_*`; prefijo obligatorio para el filtro de
migraciones; misma DB compartida con core.

Semana 2 — Ventas por peso + pedidos WhatsApp (patrón Velzia):
- `verduras_business_settings`: WhatsApp del negocio, abierto/cerrado,
  domicilio habilitado (una fila por business).
- `verduras_sales`: la venta (POS walk-in o domicilio), con idempotencia
  igual que `orders` en core (constraint único business_id+key).
- `verduras_sale_items`: líneas con cantidad por peso y SNAPSHOT de
  nombre/unidad/precio — el precio de la venta nunca cambia si el producto
  cambia de precio después (integridad contable).
- `verduras_sale_counters`: numeración atómica diaria V-YYYYMMDD-NNN
  (mismo patrón de OrderCounter en core: row lock con with_for_update).
"""
from datetime import datetime, timezone

from sqlalchemy import Date, Numeric, UniqueConstraint

from app.models import db
from app.models.core import AwareDateTime

# Unidades de venta soportadas (importado del catálogo, misma fuente de
# verdad para evitar divergencia entre catálogo y ventas).
from verduras.models import ALLOWED_UNITS  # noqa: F401  (re-export)

# Estados de una venta (máquina simple: pending → completed | cancelled).
SALE_STATUSES = ('pending', 'completed', 'cancelled')
SALE_TYPES = ('walk_in', 'delivery')
# Métodos de pago del mostrador (lista cerrada — el ticket solo MUESTRA el
# método; "libreta" es etiqueta en v1, sin ledger: el saldo por cliente
# llega con Clientes/Fiados en Semana 3. No mostrar "saldo"/"deuda" aún.
PAYMENT_METHODS = ('efectivo', 'tarjeta', 'transferencia', 'libreta')


class VerdurasBusinessSettings(db.Model):
    """Config de operación del business en este vertical (una fila por business)."""
    __tablename__ = 'verduras_business_settings'

    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), primary_key=True,
    )
    # WhatsApp de pedidos SOLO dígitos con código de país (ej: '573001234567').
    # El enlace wa.me se construye desde el backend para no depender del
    # teléfono de ningún otro modelo de core (Business no lo tiene a propósito).
    whatsapp_phone = db.Column(db.String(20))
    is_open = db.Column(db.Boolean, default=True, nullable=False,
                        server_default='1')
    delivery_enabled = db.Column(db.Boolean, default=True, nullable=False,
                                 server_default='1')
    # PIN del POS (dashboard del tendero): hash werkzeug, nunca plano.
    # El login del POS es por slug + PIN — la SERVICE_API_KEY es
    # server-to-server y JAMÁS llega al navegador.
    pos_pin_hash = db.Column(db.String(255))
    pos_pin_updated_at = db.Column(AwareDateTime)
    updated_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    business = db.relationship('Business', viewonly=True)

    def __repr__(self):
        return f'<VerdurasBusinessSettings business={self.business_id}>'


class VerdurasSale(db.Model):
    """Venta del verdulero: walk-in (POS) o delivery (pedido WhatsApp)."""
    __tablename__ = 'verduras_sales'
    __table_args__ = (
        UniqueConstraint('business_id', 'idempotency_key',
                         name='uq_verduras_sales_business_idem'),
        db.Index('ix_verduras_sales_business', 'business_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    sale_number = db.Column(db.String(20), nullable=False)  # V-20260921-001
    customer_name = db.Column(db.String(80), default='', nullable=False,
                              server_default='')
    customer_phone = db.Column(db.String(20), default='', nullable=False,
                               server_default='')
    # walk_in | delivery
    sale_type = db.Column(db.String(15), nullable=False, server_default='walk_in')
    # Método de pago (v1 POS rediseñado): efectivo | tarjeta |
    # transferencia | libreta. Nullable = ventas viejas sin dato.
    payment_method = db.Column(db.String(20), nullable=True)
    # Dueño de la deuda cuando es libreta (nullable: otros métodos y
    # ventas viejas quedan NULL con su nombre libre intacto).
    client_id = db.Column(
        db.Integer, db.ForeignKey('verduras_clientes.id'), nullable=True,
    )
    # Efectivo con control de caja: lo RECIBIDO y las VUELTAS. Solo tiene
    # sentido en efectivo; otros métodos lo dejan NULL. Sin recibido no
    # hay forma de saber si faltó o sobró plata al cuadrar.
    amount_received = db.Column(Numeric(12, 2), nullable=True)
    change_due = db.Column(Numeric(12, 2), nullable=True)
    delivery_address = db.Column(db.String(200))
    total = db.Column(Numeric(12, 2), nullable=False)
    # pending | completed | cancelled
    status = db.Column(db.String(15), nullable=False, server_default='pending')
    # Idempotencia (v1.5 de core): UUID del cliente por intento. NULL = sin
    # clave (los NULL no chocan entre sí en el constraint único).
    idempotency_key = db.Column(db.String(64))
    ip_address = db.Column(db.String(45))
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')
    completed_at = db.Column(AwareDateTime)
    cancelled_at = db.Column(AwareDateTime)

    business = db.relationship('Business', viewonly=True)
    items = db.relationship(
        'VerdurasSaleItem', back_populates='sale',
        cascade='all, delete-orphan',
        order_by='VerdurasSaleItem.id',
    )

    def __repr__(self):
        return f'<VerdurasSale {self.sale_number} ({self.status})>'


class VerdurasSaleItem(db.Model):
    """Línea de venta con snapshot contable del producto al momento de vender."""
    __tablename__ = 'verduras_sale_items'
    __table_args__ = (
        db.Index('ix_verduras_sale_items_sale', 'sale_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(
        db.Integer, db.ForeignKey('verduras_sales.id'), nullable=False,
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey('verduras_products.id'), nullable=False,
    )
    # ── Snapshot (NO son datos vivos: quedan congelados con la venta) ──
    product_name = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(10), nullable=False)
    unit_price = db.Column(Numeric(12, 2), nullable=False)
    # Peso con precisión de gramo (0.001 kg). Para 'unidad' el servicio
    # garantiza valor entero.
    quantity = db.Column(Numeric(10, 3), nullable=False)
    line_total = db.Column(Numeric(12, 2), nullable=False)

    sale = db.relationship('VerdurasSale', back_populates='items')

    def __repr__(self):
        return f'<VerdurasSaleItem {self.product_name} x{self.quantity}>'


class VerdurasCierre(db.Model):
    """Cierre Z del día: snapshot de lo vendido + conteo físico del cajón.

    v1 sin turnos: un cierre por día y negocio (unique). El esperado sale
    de las ventas no canceladas del día Bogotá; el contado lo escribe el
    tendero; la diferencia se calcula, nunca se edita. Ingresos/retiros
    de caja llegan después (requieren libro de movimientos).
    """
    __tablename__ = 'verduras_cierres'
    __table_args__ = (
        UniqueConstraint('business_id', 'day',
                         name='uq_verduras_cierres_business_day'),
        db.Index('ix_verduras_cierres_business', 'business_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    # Día operativo (America/Bogota) en formato YYYY-MM-DD.
    day = db.Column(db.String(10), nullable=False)
    # Snapshot al cerrar: total vendido y esperado en efectivo.
    total_sales = db.Column(Numeric(12, 2), nullable=False)
    cash_expected = db.Column(Numeric(12, 2), nullable=False)
    # Lo que contó el tendero en el cajón (efectivo físico).
    counted_cash = db.Column(Numeric(12, 2), nullable=False)
    # diferencia = contado − esperado (+ sobrante, − faltante).
    difference = db.Column(Numeric(12, 2), nullable=False)
    closed_at = db.Column(AwareDateTime, nullable=False,
                          default=lambda: datetime.now(timezone.utc))

    business = db.relationship('Business', viewonly=True)

    def __repr__(self):
        return (f'<VerdurasCierre {self.business_id} {self.day}: '
                f'diff={self.difference}>')


class VerdurasMovimientoCaja(db.Model):
    """Libro de caja mínimo: ingresos/retiros fuera de ventas.

    Ej: el dueño saca plata para el mercado o mete fondo en la mañana.
    Entran al esperado del cierre (efectivo + ingresos − retiros). Sin
    turnos en v1: los movimientos son del día operativo (Bogotá).
    """
    __tablename__ = 'verduras_movimientos_caja'
    __table_args__ = (
        db.Index('ix_verduras_movimientos_business_day', 'business_id',
                 'day'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    # Día operativo (America/Bogota) en formato YYYY-MM-DD.
    day = db.Column(db.String(10), nullable=False)
    # ingreso | retiro (validado en servicio).
    tipo = db.Column(db.String(10), nullable=False)
    monto = db.Column(Numeric(12, 2), nullable=False)
    motivo = db.Column(db.String(120))
    registered_at = db.Column(AwareDateTime, nullable=False,
                              default=lambda: datetime.now(timezone.utc))

    business = db.relationship('Business', viewonly=True)

    def __repr__(self):
        return (f'<VerdurasMovimientoCaja {self.business_id} {self.day}: '
                f'{self.tipo} {self.monto}>')


class VerdurasCliente(db.Model):
    """Cuenta de fiado del vecino (libreta): el dueño le fía, él abona.

    Sin roles en v1: nace desde la venta (elegir/crear al cobrar con
    libreta). Duplicado de nombre en el mismo negocio se reutiliza, no se
    duplica. La deuda NUNCA se almacena: se deriva (fiados − abonos).
    """
    __tablename__ = 'verduras_clientes'
    __table_args__ = (
        UniqueConstraint('business_id', 'name',
                         name='uq_verduras_clientes_business_name'),
        db.Index('ix_verduras_clientes_business', 'business_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    # Fecha de compromiso de pago (una por cuenta, v1). Nullable = sin fecha.
    fecha_compromiso = db.Column(Date)
    # Cupo de crédito autorizado (fiados v2). NULL = sin límite definido:
    # las cuentas viejas (y los que no quieren techo) quedan como están.
    credit_limit = db.Column(Numeric(12, 2), nullable=True)
    # Nota interna del tendero sobre el cliente (v2). Nunca sale del POS.
    internal_note = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, nullable=False,
                          server_default='1')
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    business = db.relationship('Business', viewonly=True)

    def __repr__(self):
        return f'<VerdurasCliente {self.name} (business {self.business_id})>'


class VerdurasAbono(db.Model):
    """Pago parcial contra la deuda (la otra pata del saldo derivado)."""
    __tablename__ = 'verduras_abonos'
    __table_args__ = (
        db.Index('ix_verduras_abonos_client', 'client_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    client_id = db.Column(
        db.Integer, db.ForeignKey('verduras_clientes.id'), nullable=False,
    )
    monto = db.Column(Numeric(12, 2), nullable=False)
    note = db.Column(db.String(255))
    # Método con que entró el dinero: efectivo | transferencia | tarjeta.
    # NULL = abonos viejos (v1) registrados sin método.
    method = db.Column(db.String(20), nullable=True)
    registered_at = db.Column(AwareDateTime, nullable=False,
                              default=lambda: datetime.now(timezone.utc))

    business = db.relationship('Business', viewonly=True)
    client = db.relationship('VerdurasCliente', viewonly=True)

    def __repr__(self):
        return (f'<VerdurasAbono cliente={self.client_id}: {self.monto}>')


class VerdurasSaleCounter(db.Model):
    """Contador diario de números de venta por business (numeración atómica)."""
    __tablename__ = 'verduras_sale_counters'
    __table_args__ = (
        db.PrimaryKeyConstraint('business_id', 'date',
                                name='pk_verduras_sale_counters'),
    )

    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), primary_key=True,
    )
    date = db.Column(Date, nullable=False, primary_key=True)
    last_number = db.Column(db.Integer, nullable=False, server_default='0',
                            default=0)

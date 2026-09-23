"""
Models de inventario y merma del vertical Verduras (Semana 3).

⚠️ Mismo contrato que verduras/models.py: FKs solo a `businesses.id` o a
tablas propias `verduras_*`; prefijo obligatorio para el filtro de
migraciones; misma DB compartida con core.

Semana 3 — Inventario por lotes + Merma (la joya del producto):
- `verduras_lots`: compras por lote ("50kg de tomate a $X"). El costo por
  kg/unidad NO se guarda: se deriva (total_cost / quantity) para que jamás
  diverja de los datos reales.
- `verduras_merma`: kilos dañados por producto, con la PÉRDIDA en COP
  congelada al momento de registrar (snapshot contable, igual que las
  líneas de venta). El reporte semanal/mensual se construye desde aquí.

El stock en tiempo real NO se almacena: se DERIVA como
compras − ventas − merma ± ajustes (servicio inventory.py). Derivarlo
evita la clase entera de bugs de sincronización y hace el dato auditable.
"""
from datetime import datetime, timezone

from sqlalchemy import Numeric

from app.models import db
from app.models.core import AwareDateTime

# Motivos de merma soportados (validado en el servicio, sin CHECK en DB
# para máxima compatibilidad sqlite/MySQL/MariaDB). Etiquetas legibles en
# MERMA_REASON_LABELS para la API/frontend.
MERMA_REASONS = ('danado', 'vencido', 'golpeado', 'otro')
MERMA_REASON_LABELS = {
    'danado': 'Dañado',
    'vencido': 'Vencido',
    'golpeado': 'Golpeado',
    'otro': 'Otro',
}


class VerdurasLot(db.Model):
    """Lote de compra: "50kg de tomate que llegaron el martes a $90.000"."""
    __tablename__ = 'verduras_lots'
    __table_args__ = (
        db.Index('ix_verduras_lots_business_product', 'business_id',
                 'product_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey('verduras_products.id'), nullable=False,
    )
    # Cantidad comprada EN LA UNIDAD DEL PRODUCTO (kg, lb o unidades).
    # Misma precisión que las líneas de venta (gramo = 0.001).
    quantity = db.Column(Numeric(12, 3), nullable=False)
    # Lo que pagó por el lote COMPLETO (COP). El costo unitario se deriva.
    total_cost = db.Column(Numeric(12, 2), nullable=False)
    purchased_at = db.Column(AwareDateTime, nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    # Proveedor u observación libre (ej: "Finza La Loma - x 50kg").
    note = db.Column(db.String(255))
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    business = db.relationship('Business', viewonly=True)
    product = db.relationship('VerdurasProduct', viewonly=True)

    @property
    def unit_cost(self):
        """Costo por kg/lb/unidad derivado del lote (jamás almacenado)."""
        from decimal import ROUND_HALF_UP, Decimal
        if not self.quantity:
            return None
        return (Decimal(str(self.total_cost)) / Decimal(str(self.quantity))
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def __repr__(self):
        return (f'<VerdurasLot {self.product_id}: '
                f'{self.quantity} x ${self.total_cost}>')


class VerdurasMerma(db.Model):
    """Producto perdido: dañado, vencido o golpeado, con su costo en COP."""
    __tablename__ = 'verduras_merma'
    __table_args__ = (
        db.Index('ix_verduras_merma_business_product', 'business_id',
                 'product_id'),
        db.Index('ix_verduras_merma_registered', 'business_id',
                 'registered_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey('verduras_products.id'), nullable=False,
    )
    # Cantidad perdida EN LA UNIDAD DEL PRODUCTO.
    quantity = db.Column(Numeric(12, 3), nullable=False)
    # danado | vencido | golpeado | otro (validado en servicio).
    reason = db.Column(db.String(20), nullable=False, server_default='danado')
    # PÉRDIDA EN COP congelada al registrar (quantity × costo promedio del
    # producto, o el unit_cost manual si no hay lotes). Snapshot contable:
    # si mañana cambia el costo de compra, el histórico NO se re-escribe.
    cost_loss = db.Column(Numeric(12, 2), nullable=False)
    registered_at = db.Column(AwareDateTime, nullable=False,
                              default=lambda: datetime.now(timezone.utc))
    note = db.Column(db.String(255))
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    business = db.relationship('Business', viewonly=True)
    product = db.relationship('VerdurasProduct', viewonly=True)

    def __repr__(self):
        return (f'<VerdurasMerma {self.product_id}: {self.quantity} '
                f'({self.reason})>')


# Motivos de ajuste soportados (conteo físico y correcciones; validado en
# el servicio, sin CHECK en DB como MERMA_REASONS).
AJUSTE_MOTIVOS = ('conteo', 'error_pesaje', 'otro')
AJUSTE_MOTIVO_LABELS = {
    'conteo': 'Conteo físico',
    'error_pesaje': 'Error de pesaje',
    'otro': 'Otro',
}


class VerdurasAjuste(db.Model):
    """Corrección de stock FIRMADA: el dueño contó y el sistema cuadra.

    Guarda anterior + contado + diferencia (con signo: + sobrante,
    − faltante) + motivo + fecha. El stock se DERIVA incluyendo ajustes:
    compras − ventas − merma ± ajustes. Ajustar NUNCA re-escribe historia:
    es un movimiento más, auditable. Sin ajuste no hay forma honesta de
    corregir un conteo (la alternativa sería mentir con compras falsas).
    """
    __tablename__ = 'verduras_ajustes'
    __table_args__ = (
        db.Index('ix_verduras_ajustes_business_product', 'business_id',
                 'product_id'),
        db.Index('ix_verduras_ajustes_registered', 'business_id',
                 'registered_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey('verduras_products.id'), nullable=False,
    )
    # Stock del sistema ANTES del ajuste, en la unidad del producto.
    stock_before = db.Column(Numeric(12, 3), nullable=False)
    # Lo que el dueño contó físicamente.
    counted = db.Column(Numeric(12, 3), nullable=False)
    # Diferencia con signo (counted − stock_before). NUNCA cero.
    delta = db.Column(Numeric(12, 3), nullable=False)
    # conteo | error_pesaje | otro (validado en servicio).
    motivo = db.Column(db.String(20), nullable=False,
                       server_default='conteo')
    note = db.Column(db.String(255))
    registered_at = db.Column(AwareDateTime, nullable=False,
                              default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    business = db.relationship('Business', viewonly=True)
    product = db.relationship('VerdurasProduct', viewonly=True)

    def __repr__(self):
        return (f'<VerdurasAjuste {self.product_id}: {self.delta} '
                f'({self.motivo})>')

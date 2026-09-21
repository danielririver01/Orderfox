"""
Models del vertical Verduras.

⚠️ Contrato del monorepo (verduras/README.md):
- Toda FK apunta a `businesses.id` o a tablas propias `verduras_*`.
  NUNCA se crean FKs hacia `restaurants` — el espejo existe y los IDs
  alinean, pero la frontera core/módulo vive en `business_id`.
- Los nombres de tablas, índices y constraints llevan prefijo `verduras_`:
  el filtro include_object de verduras/migrations/env.py depende de ello.
- La DB es la compartida de core (verduras.extensions.db): estas tablas se
  registran en el MISMO metadata y conviven con las de core.

Semana 1 — Catálogo + precios por peso:
- `verduras_categories`: categorías por business (Hortalizas, Frutas, ...).
- `verduras_products`: precio por KG / LB / Unidad con foto.
- `verduras_price_history`: curva histórica de precios (la joya del producto:
  el verdulero cambia precios a diario y nadie más le guarda la serie).
"""
from datetime import datetime, timezone

from sqlalchemy import Numeric, UniqueConstraint

from app.models import db
from app.models.core import AwareDateTime

# Unidades de venta soportadas (validado en el servicio, sin CHECK en DB
# para máxima compatibilidad sqlite/MySQL/MariaDB).
ALLOWED_UNITS = ('kg', 'lb', 'unidad')


class VerdurasCategory(db.Model):
    __tablename__ = 'verduras_categories'
    __table_args__ = (
        UniqueConstraint('business_id', 'name',
                         name='uq_verduras_categories_business_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    name = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False,
                          server_default='1')
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    products = db.relationship(
        'VerdurasProduct', back_populates='category',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<VerdurasCategory {self.name} (business {self.business_id})>'


class VerdurasProduct(db.Model):
    __tablename__ = 'verduras_products'
    __table_args__ = (
        UniqueConstraint('business_id', 'name',
                         name='uq_verduras_products_business_name'),
        db.Index('ix_verduras_products_business', 'business_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey('businesses.id'), nullable=False,
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey('verduras_categories.id'), nullable=False,
    )
    name = db.Column(db.String(120), nullable=False)
    # kg | lb | unidad (validado en servicio; default server para DDL directa)
    unit = db.Column(db.String(10), nullable=False, server_default='kg')
    current_price = db.Column(Numeric(12, 2), nullable=False)
    # Umbral de alerta de rotación (Semana 5). NULL = sin alerta (opt-in:
    # solo los productos que el tendero quiere vigilar generan alertas).
    # Misma precisión que las cantidades: gramo (0.001).
    min_stock = db.Column(Numeric(12, 3), nullable=True)
    photo_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, nullable=False,
                          server_default='1')
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')
    updated_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    category = db.relationship('VerdurasCategory', back_populates='products')
    price_history = db.relationship(
        'VerdurasPriceHistory', back_populates='product',
        cascade='all, delete-orphan',
        # Más nuevo primero; id.desc() como desempate determinista (MySQL
        # trunca microsegundos: dos precios del mismo segundo empatarían).
        order_by='VerdurasPriceHistory.effective_from.desc(), '
                 'VerdurasPriceHistory.id.desc()',
    )

    def __repr__(self):
        return f'<VerdurasProduct {self.name} ({self.unit})>'


class VerdurasPriceHistory(db.Model):
    __tablename__ = 'verduras_price_history'
    __table_args__ = (
        db.Index('ix_verduras_price_history_product', 'product_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey('verduras_products.id'), nullable=False,
    )
    price = db.Column(Numeric(12, 2), nullable=False)
    effective_from = db.Column(AwareDateTime, nullable=False,
                               default=lambda: datetime.now(timezone.utc))
    # manual | bascula | importacion (futuras fuentes, misma columna)
    source = db.Column(db.String(20), nullable=False, server_default='manual')
    note = db.Column(db.String(255))
    created_at = db.Column(AwareDateTime,
                           default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    product = db.relationship('VerdurasProduct', back_populates='price_history')

    def __repr__(self):
        return f'<VerdurasPriceHistory {self.product_id}: {self.price}>'

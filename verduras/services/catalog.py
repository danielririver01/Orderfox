"""
Servicio de catálogo del vertical Verduras (Semana 1).

Toda la lógica de negocio del catálogo vive aquí; las rutas solo orquestan
(convención del repo). Reglas:
- Unidades válidas: kg | lb | unidad (se normalizan a minúsculas).
- Precios: Decimal cuantizado a 2 decimales, siempre > 0.
- Cada producto nace con su PRIMERA fila de historial (baseline del precio).
- Cambiar precio = actualizar current_price + append al historial.
  Si el precio nuevo es igual al vigente se rechaza (fila de ruido evitada).
- Todo acceso queda scoping por business_id (anti-IDOR): pedir el producto
  de otro business es como no existir.
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app.models import db
from verduras.models import (
    ALLOWED_UNITS,
    VerdurasCategory,
    VerdurasPriceHistory,
    VerdurasProduct,
)

_CENTS = Decimal('0.01')


class VerdurasValidationError(ValueError):
    """Datos inválidos o regla de negocio incumplida."""


class VerdurasNotFoundError(LookupError):
    """Recurso inexistente (o de otro business)."""


def _parse_price(value) -> Decimal:
    """Convierte a Decimal(2 dec, ROUND_HALF_UP) y valida > 0."""
    if value is None:
        raise VerdurasValidationError('El precio es requerido')
    try:
        price = Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(f'Precio inválido: {value!r}')
    if price <= 0:
        raise VerdurasValidationError('El precio debe ser mayor a 0')
    return price


def _normalize_unit(unit) -> str:
    if not unit:
        raise VerdurasValidationError('La unidad es requerida (kg|lb|unidad)')
    unit = str(unit).strip().lower()
    if unit not in ALLOWED_UNITS:
        raise VerdurasValidationError(
            f"Unidad inválida: '{unit}'. Válidas: {', '.join(ALLOWED_UNITS)}"
        )
    return unit


def _normalize_name(name) -> str:
    if not name or not str(name).strip():
        raise VerdurasValidationError('El nombre es requerido')
    return str(name).strip()


# ── Categorías ──────────────────────────────────────────────


def list_categories(business_id: int, include_inactive: bool = False):
    query = VerdurasCategory.query.filter_by(business_id=business_id)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return query.order_by(VerdurasCategory.name).all()


def create_category(business_id: int, name: str) -> VerdurasCategory:
    name = _normalize_name(name)
    exists = VerdurasCategory.query.filter_by(
        business_id=business_id, name=name).first()
    if exists:
        raise VerdurasValidationError(
            f"La categoría '{name}' ya existe en este business")
    category = VerdurasCategory(business_id=business_id, name=name)
    db.session.add(category)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise VerdurasValidationError(
            f"La categoría '{name}' ya existe en este business")
    return category


# ── Productos ───────────────────────────────────────────────


def get_product(business_id: int, product_id: int) -> VerdurasProduct | None:
    """Anti-IDOR: solo productos del business dado."""
    product = db.session.get(VerdurasProduct, product_id)
    if product is None or product.business_id != business_id:
        return None
    return product


def list_products(business_id: int, category_id: int | None = None,
                  include_inactive: bool = False):
    query = VerdurasProduct.query.filter_by(business_id=business_id)
    if category_id is not None:
        query = query.filter_by(category_id=category_id)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return query.order_by(VerdurasProduct.name).all()


def create_product(business_id: int, category_id: int, name: str, unit: str,
                   price, photo_url: str | None = None,
                   source: str = 'manual') -> VerdurasProduct:
    name = _normalize_name(name)
    unit = _normalize_unit(unit)
    price = _parse_price(price)

    category = db.session.get(VerdurasCategory, category_id)
    if category is None or category.business_id != business_id:
        raise VerdurasNotFoundError('Categoría no encontrada')

    exists = VerdurasProduct.query.filter_by(
        business_id=business_id, name=name).first()
    if exists:
        raise VerdurasValidationError(
            f"El producto '{name}' ya existe en este business")

    product = VerdurasProduct(
        business_id=business_id, category_id=category.id,
        name=name, unit=unit, current_price=price, photo_url=photo_url,
    )
    # Baseline del historial: todo precio vigente tiene origen registrado.
    product.price_history.append(VerdurasPriceHistory(
        price=price, effective_from=datetime.now(timezone.utc),
        source=source,
    ))
    db.session.add(product)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise VerdurasValidationError(
            f"El producto '{name}' ya existe en este business")
    return product


def update_price(business_id: int, product_id: int, new_price,
                 source: str = 'manual', note: str | None = None
                 ) -> VerdurasProduct:
    """Cambio de precio con historial (el flujo diario del verdulero)."""
    price = _parse_price(new_price)
    product = get_product(business_id, product_id)
    if product is None:
        raise VerdurasNotFoundError('Producto no encontrado')
    if product.current_price == price:
        raise VerdurasValidationError(
            f'El precio ya es {price:.2f}; no hay cambio que registrar')

    product.current_price = price
    product.price_history.append(VerdurasPriceHistory(
        price=price, effective_from=datetime.now(timezone.utc),
        source=source, note=note,
    ))
    db.session.commit()
    return product

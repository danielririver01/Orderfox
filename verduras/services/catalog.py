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


def _has_movements(business_id: int, product_id: int) -> bool:
    """True si el producto ya movió inventario (lotes, ventas o merma).

    Puerta de las reglas contables: con movimientos, la unidad es
    intocable y el borrado físico está prohibido (solo soft).
    """
    from verduras.models_inventory import VerdurasLot, VerdurasMerma
    from verduras.models_sales import VerdurasSale, VerdurasSaleItem
    if VerdurasLot.query.filter_by(
            business_id=business_id, product_id=product_id).first():
        return True
    if VerdurasSaleItem.query.join(VerdurasSale).filter(
            VerdurasSale.business_id == business_id,
            VerdurasSaleItem.product_id == product_id).first():
        return True
    return VerdurasMerma.query.filter_by(
        business_id=business_id, product_id=product_id).first() is not None


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
    if exists is not None and exists.is_active:
        raise VerdurasValidationError(
            f"El producto '{name}' ya existe en este business")
    if exists is not None:
        # Recrear tras eliminar = REACTIVAR (eliminar es soft: la fila
        # sigue con su historial). Unidad intocable si ya tuvo movimientos:
        # rompería stock e historial igual que en update_product.
        if exists.unit != unit and _has_movements(business_id, exists.id):
            raise VerdurasValidationError(
                f"'{name}' existe desactivado en {exists.unit}: no se puede "
                f"recrear en {unit} (rompería su historial). Usa otro nombre.")
        exists.is_active = True
        exists.category_id = category.id
        exists.unit = unit
        db.session.commit()
        if exists.current_price != price:
            return update_price(business_id, exists.id, price,
                                source=source)
        return exists

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


def rename_category(business_id: int, category_id: int, name
                    ) -> VerdurasCategory:
    """Renombra una categoría. Siempre seguro: no toca FKs ni historial."""
    category = db.session.get(VerdurasCategory, category_id)
    if category is None or category.business_id != business_id:
        raise VerdurasNotFoundError('Categoría no encontrada')
    name = _normalize_name(name)
    dup = VerdurasCategory.query.filter_by(
        business_id=business_id, name=name).first()
    if dup is not None and dup.id != category.id:
        raise VerdurasValidationError(
            f"La categoría '{name}' ya existe en este business")
    category.name = name
    db.session.commit()
    return category


def delete_category(business_id: int, category_id: int,
                    move_to_category_id=None) -> dict:
    """Elimina una categoría, moviendo sus productos si se pide destino.

    - Vacía → se elimina sin más.
    - Con productos y SIN destino → bloqueado (borrarla arrastraría
      productos por cascade y rompería historial). El error trae el conteo
      para que el frontend ofrezca el destino.
    - Con destino válido del mismo business → reasigna TODOS (activos e
      inactivos, el historial no se toca: solo cambia la etiqueta) y
      elimina, todo en una transacción.
    """
    category = db.session.get(VerdurasCategory, category_id)
    if category is None or category.business_id != business_id:
        raise VerdurasNotFoundError('Categoría no encontrada')
    prods = VerdurasProduct.query.filter_by(
        business_id=business_id, category_id=category.id).all()
    moved = 0
    if prods:
        if move_to_category_id is None:
            raise VerdurasValidationError(
                f"'{category.name}' tiene {len(prods)} producto(s): elige "
                f"a qué categoría moverlos", )
        try:
            move_to_id = int(move_to_category_id)
        except (TypeError, ValueError):
            raise VerdurasValidationError('Categoría destino inválida')
        if move_to_id == category.id:
            raise VerdurasValidationError(
                'El destino no puede ser la misma categoría')
        target = db.session.get(VerdurasCategory, move_to_id)
        if target is None or target.business_id != business_id:
            raise VerdurasNotFoundError('Categoría destino no encontrada')
        for p in prods:
            p.category_id = target.id
            moved += 1
    db.session.delete(category)
    db.session.commit()
    return {'deleted': True, 'moved': moved}


def update_product(business_id: int, product_id: int, *,
                   name=None, category_id=None, is_active=None
                   ) -> VerdurasProduct:
    """Edición de ficha (nombre/categoría/activo). Segura por diseño:
    - Unidad JAMÁS editable aquí: rompería stock e historial (kg≠unidad).
      ¿Unidad mal? Desactivar y crear el producto de nuevo.
    - Nombre único por business (mismo constraint que create, excluyéndose).
    - Los tickets viejos no se tocan: guardan snapshot por venta.
    """
    product = get_product(business_id, product_id)
    if product is None:
        raise VerdurasNotFoundError('Producto no encontrado')
    if name is not None:
        name = _normalize_name(name)
        dup = VerdurasProduct.query.filter_by(
            business_id=business_id, name=name).first()
        if dup is not None and dup.id != product.id:
            raise VerdurasValidationError(
                f"El producto '{name}' ya existe en este business")
        product.name = name
    if category_id is not None:
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise VerdurasValidationError('Categoría inválida')
        category = db.session.get(VerdurasCategory, category_id)
        if category is None or category.business_id != business_id:
            raise VerdurasNotFoundError('Categoría no encontrada')
        product.category_id = category.id
    if is_active is not None:
        product.is_active = bool(is_active)
    db.session.commit()
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

"""
Servicio de inventario y merma del vertical Verduras (Semana 3).

Filosofía (misma del módulo): la DB calcula, el servicio organiza.
- El stock NO se almacena: se DERIVA como compras − ventas − merma
  ± ajustes. Derivarlo elimina la clase entera de bugs de sincronización
  y hace el dato auditable (siempre se puede reconstruir desde los
  movimientos).
- El costo por kg de un lote NO se guarda: se deriva (total / cantidad).
- El costo de referencia del producto es el PROMEDIO PONDERADO de sus
  lotes (no el último): 30kg a $1.500 + 20kg a $2.500 → 50kg a $1.900.
- La pérdida de merma se congela en COP al registrarla (snapshot contable,
  igual que las líneas de venta: el histórico no se re-escribe).

Toda la lógica vive aquí; las rutas solo orquestan (convención del repo).
"""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func

from app.models import db
from verduras.models import VerdurasProduct
from verduras.models_inventory import (
    AJUSTE_MOTIVOS,
    MERMA_REASONS,
    VerdurasAjuste,
    VerdurasLot,
    VerdurasMerma,
)
from verduras.models_sales import VerdurasSale, VerdurasSaleItem

_CENTS = Decimal('0.01')
_MILLIS = Decimal('0.001')


class VerdurasValidationError(ValueError):
    """Datos inválidos o regla de negocio incumplida."""


class VerdurasNotFoundError(LookupError):
    """Recurso inexistente (o de otro business)."""


# ── Helpers de validación ───────────────────────────────────


def _parse_positive_qty(value):
    """Cantidad en la unidad del producto, precisión de gramo (0.001)."""
    if value is None:
        raise VerdurasValidationError('La cantidad es requerida')
    try:
        raw = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(f'Cantidad inválida: {value!r}')
    if raw <= 0:
        raise VerdurasValidationError('La cantidad debe ser mayor a 0')
    qty = raw.quantize(_MILLIS, rounding=ROUND_HALF_UP)
    if qty == 0:
        raise VerdurasValidationError('Cantidad mínima: 0.001 (1 gramo)')
    return qty


def _parse_cost(value, field='costo'):
    """Monto en COP cuantizado a centavos y > 0."""
    if value is None:
        raise VerdurasValidationError(f'El {field} es requerido')
    try:
        cost = Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(f'{field.capitalize()} inválido: {value!r}')
    if cost <= 0:
        raise VerdurasValidationError(f'El {field} debe ser mayor a 0')
    return cost


def _parse_reason(value) -> str:
    reason = str(value or 'danado').strip().lower()
    if reason not in MERMA_REASONS:
        raise VerdurasValidationError(
            f"Motivo de merma inválido: '{reason}'. "
            f"Válidos: {', '.join(MERMA_REASONS)}")
    return reason


def _parse_day(value, field: str):
    """Fecha 'YYYY-MM-DD' → date (UTC); vacío → None."""
    if value is None or value == '':
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').replace(
            tzinfo=timezone.utc).date()
    except ValueError:
        raise VerdurasValidationError(
            f"Fecha inválida en '{field}' (usa YYYY-MM-DD)")


def _range_utc(day_from, day_to):
    """Rango [inicio, fin) en UTC a partir de fechas 'YYYY-MM-DD'."""
    start = datetime.combine(day_from, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(
        day_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return start, end


def _parse_moment(value, field: str):
    """Datetime opcional: None → ahora (UTC); ISO o 'YYYY-MM-DD'; naive = UTC."""
    if value is None or value == '':
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            raise VerdurasValidationError(
                f"Fecha inválida en '{field}' (usa ISO 8601 o YYYY-MM-DD)")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── Anti-IDOR ───────────────────────────────────────────────


def _get_product(business_id: int, product_id: int) -> VerdurasProduct:
    """Producto del business dado; de otro business = no existe (anti-IDOR)."""
    product = db.session.get(VerdurasProduct, product_id)
    if product is None or product.business_id != business_id:
        raise VerdurasNotFoundError('Producto no encontrado')
    return product


# ── Lotes de compra ─────────────────────────────────────────


def register_lot(business_id: int, product_id: int, quantity,
                 total_cost, purchased_at=None, note=None) -> VerdurasLot:
    """Registra una compra por lote ("50kg de tomate a $90.000").

    El costo unitario NO se pasa: se deriva del lote (total / cantidad).
    """
    product = _get_product(business_id, product_id)
    qty = _parse_positive_qty(quantity)
    cost = _parse_cost(total_cost)
    moment = _parse_moment(purchased_at, 'purchased_at')

    lot = VerdurasLot(
        business_id=business_id,
        product_id=product.id,
        quantity=qty,
        total_cost=cost,
        purchased_at=moment,
        note=(note or '').strip() or None,
    )
    db.session.add(lot)
    db.session.commit()
    return lot


def list_lots(business_id: int, product_id: int | None = None,
              limit: int = 100) -> list[VerdurasLot]:
    """Lotes del business (más nuevos primero), opcionalmente de un producto."""
    query = VerdurasLot.query.filter_by(business_id=business_id)
    if product_id is not None:
        query = query.filter_by(product_id=product_id)
    return (query.order_by(VerdurasLot.purchased_at.desc(), VerdurasLot.id.desc())
            .limit(min(int(limit), 500)).all())


# ── Costo promedio ponderado ────────────────────────────────


def average_unit_cost(business_id: int, product_id: int,
                      until: datetime | None = None) -> Decimal | None:
    """Costo unitario ponderado por los lotes del producto.

    Pondera por CANTIDAD, no por lote: 30kg a $45.000 + 20kg a $50.000
    → $47.00/kg... el promedio simple daría $47.500 (inflado).
    None si el producto no tiene lotes aún.
    """
    query = db.session.query(
        func.sum(VerdurasLot.quantity), func.sum(VerdurasLot.total_cost),
    ).filter(
        VerdurasLot.business_id == business_id,
        VerdurasLot.product_id == product_id,
    )
    if until is not None:
        query = query.filter(VerdurasLot.purchased_at <= until)
    total_qty, total_cost = query.one()
    total_qty = Decimal(str(total_qty or 0))
    total_cost = Decimal(str(total_cost or 0))
    if total_qty <= 0:
        return None
    return (total_cost / total_qty).quantize(_CENTS, rounding=ROUND_HALF_UP)


# ── Stock derivado ──────────────────────────────────────────


def _sum_sales(business_id: int, product_id: int, until=None, since=None):
    """Kg/lb/unidades vendidas del producto (ventas no canceladas).

    `since`/`until` delimitan la ventana por created_at (Semana 5: la
    velocidad de venta de las alertas usa esta misma fuente — la
    semántica de "qué cuenta como vendido" vive SOLO aquí).
    """
    query = db.session.query(func.sum(VerdurasSaleItem.quantity)).join(
        VerdurasSale, VerdurasSale.id == VerdurasSaleItem.sale_id,
    ).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSaleItem.product_id == product_id,
        VerdurasSale.status != 'cancelled',
    )
    if until is not None:
        query = query.filter(VerdurasSale.created_at <= until)
    if since is not None:
        query = query.filter(VerdurasSale.created_at > since)
    return Decimal(str(query.scalar() or 0))


def _sum_purchased(business_id: int, product_id: int, until):
    query = db.session.query(func.sum(VerdurasLot.quantity)).filter(
        VerdurasLot.business_id == business_id,
        VerdurasLot.product_id == product_id,
    )
    if until is not None:
        query = query.filter(VerdurasLot.purchased_at <= until)
    return Decimal(str(query.scalar() or 0))


def _sum_merma(business_id: int, product_id: int, until):
    query = db.session.query(func.sum(VerdurasMerma.quantity)).filter(
        VerdurasMerma.business_id == business_id,
        VerdurasMerma.product_id == product_id,
    )
    if until is not None:
        query = query.filter(VerdurasMerma.registered_at <= until)
    return Decimal(str(query.scalar() or 0))


def _sum_ajustes(business_id: int, product_id: int, until):
    """Suma firmada de ajustes (deltas +/− por conteos físicos)."""
    query = db.session.query(func.sum(VerdurasAjuste.delta)).filter(
        VerdurasAjuste.business_id == business_id,
        VerdurasAjuste.product_id == product_id,
    )
    if until is not None:
        query = query.filter(VerdurasAjuste.registered_at <= until)
    return Decimal(str(query.scalar() or 0))


def _parse_motivo(value) -> str:
    motivo = str(value or 'conteo').strip().lower()
    if motivo not in AJUSTE_MOTIVOS:
        raise VerdurasValidationError(
            f"Motivo de ajuste inválido: '{motivo}'. "
            f"Válidos: {', '.join(AJUSTE_MOTIVOS)}")
    return motivo


def register_ajuste(business_id: int, product_id: int, counted,
                    motivo='conteo', note=None) -> VerdurasAjuste:
    """Corrección de stock FIRMADA por conteo físico (filosofía Velzia:
    "puedes corregirlo, pero Velzia registra que fue una corrección").

    El dueño ingresa lo que CONTÓ; el backend calcula la diferencia contra
    el stock del sistema. Delta cero se rechaza (no hay nada que corregir).
    El ajuste NUNCA re-escribe historia: es un movimiento más, con anterior
    + contado + diferencia con signo + motivo + fecha.
    """
    product = _get_product(business_id, product_id)
    try:
        counted = Decimal(str(counted)).quantize(
            _MILLIS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(
            f'Cantidad contada inválida: {counted!r}')
    if counted < 0:
        raise VerdurasValidationError(
            'Lo contado no puede ser negativo')
    motivo = _parse_motivo(motivo)
    # stock actual como Decimal (get_stock lo devuelve str).
    current = Decimal(get_stock(business_id, product.id)['stock'])
    delta = (counted - current).quantize(_MILLIS, rounding=ROUND_HALF_UP)
    if delta == 0:
        raise VerdurasValidationError(
            f'Lo contado ({counted} {product.unit}) iguala el stock del '
            f'sistema: no hay nada que ajustar')
    ajuste = VerdurasAjuste(
        business_id=business_id,
        product_id=product.id,
        stock_before=current,
        counted=counted,
        delta=delta,
        motivo=motivo,
        note=(note or '').strip() or None,
    )
    db.session.add(ajuste)
    db.session.commit()
    return ajuste


def get_stock(business_id: int, product_id: int, until=None) -> dict:
    """Stock en tiempo real DERIVADO: compras − ventas − merma ± ajustes.

    Incluye el valor del stock (stock × costo promedio ponderado) cuando
    hay lotes: lo que el tendero tiene parado en la trakta, en COP.
    """
    product = _get_product(business_id, product_id)
    moment = _parse_moment(until, 'until') if until not in (None, '') else None

    purchased = _sum_purchased(business_id, product.id, moment)
    sold = _sum_sales(business_id, product.id, moment)
    lost = _sum_merma(business_id, product.id, moment)
    adjusted = _sum_ajustes(business_id, product.id, moment)
    stock = (purchased - sold - lost + adjusted).quantize(
        _MILLIS, rounding=ROUND_HALF_UP)

    avg_cost = average_unit_cost(business_id, product.id, until=moment)
    return {
        'product_id': product.id,
        'name': product.name,
        'unit': product.unit,
        'purchased': str(purchased),
        'sold': str(sold),
        'merma': str(lost),
        'ajustes': str(adjusted),
        'stock': str(stock),
        'avg_unit_cost': str(avg_cost) if avg_cost is not None else None,
        'stock_value': (str((stock * avg_cost).quantize(
            _CENTS, rounding=ROUND_HALF_UP))
            if avg_cost is not None and stock > 0 else None),
    }


def list_stock(business_id: int, until=None) -> list[dict]:
    """Stock de todos los productos activos, ordenado por nombre.

    Nota: una query derivada por producto — a escala tendero (decenas de
    productos) es imperceptible y mantiene el cálculo legible/auditable.
    """
    products = (VerdurasProduct.query.filter_by(
        business_id=business_id, is_active=True)
        .order_by(VerdurasProduct.name).all())
    return [get_stock(business_id, p.id, until) for p in products]


# ── Merma ───────────────────────────────────────────────────


def register_merma(business_id: int, product_id: int, quantity, reason='danado',
                   note=None, unit_cost=None) -> VerdurasMerma:
    """Registra producto perdido con su PÉRDIDA EN COP congelada.

    El costo unitario es el promedio ponderado de los lotes; si el
    producto aún no tiene lotes se puede pasar `unit_cost` manual
    (el verdulero sabe cuánto le costó) — sin lotes ni manual, se rechaza
    para no inventar pérdidas en cero.
    """
    product = _get_product(business_id, product_id)
    qty = _parse_positive_qty(quantity)
    motive = _parse_reason(reason)

    avg = average_unit_cost(business_id, product.id)
    if avg is not None:
        cost = avg
    elif unit_cost is not None:
        cost = _parse_cost(unit_cost, 'costo unitario')
    else:
        raise VerdurasValidationError(
            'El producto no tiene lotes de compra registrados: pasa el '
            'costo unitario manual o registra primero la compra')

    merma = VerdurasMerma(
        business_id=business_id,
        product_id=product.id,
        quantity=qty,
        reason=motive,
        cost_loss=(qty * cost).quantize(_CENTS, rounding=ROUND_HALF_UP),
        note=(note or '').strip() or None,
    )
    db.session.add(merma)
    db.session.commit()
    return merma


def list_merma(business_id: int, product_id: int | None = None,
               day_from=None, day_to=None) -> list[VerdurasMerma]:
    """Registros de merma, más nuevos primero, con filtros opcionales."""
    query = VerdurasMerma.query.filter_by(business_id=business_id)
    if product_id is not None:
        query = query.filter_by(product_id=product_id)
    day_f = _parse_day(day_from, 'date_from')
    day_t = _parse_day(day_to, 'date_to')
    if day_f or day_t:
        start, end = _range_utc(
            day_f or datetime.now(timezone.utc).date(),
            day_t or datetime.now(timezone.utc).date())
        query = query.filter(VerdurasMerma.registered_at >= start,
                             VerdurasMerma.registered_at < end)
    return (query.order_by(VerdurasMerma.registered_at.desc(),
                           VerdurasMerma.id.desc()).all())


# ── Reporte semanal/mensual (la joya) ───────────────────────


def merma_report(business_id: int, day_from, day_to) -> dict:
    """Reporte de merma del período: pérdida por producto, % y contexto.

    - total_loss: pérdida total del período en COP (snapshot, no se mueve).
    - pct_of_loss: cuánto aporta cada producto a la pérdida total.
    - purchases_cost: cuánto compró en el período → merma_pct_of_purchases
      dice qué fracción de la compra se perdió (el indicador que el
      verdulero quiere bajar semana a semana).
    """
    day_f = _parse_day(day_from, 'date_from')
    day_t = _parse_day(day_to, 'date_to')
    if not day_f or not day_t:
        raise VerdurasValidationError(
            'El reporte requiere date_from y date_to (YYYY-MM-DD)')
    if day_t < day_f:
        raise VerdurasValidationError(
            'date_to no puede ser anterior a date_from')
    start, end = _range_utc(day_f, day_t)

    rows = (db.session.query(
        VerdurasMerma.product_id,
        VerdurasProduct.name,
        VerdurasProduct.unit,
        func.sum(VerdurasMerma.quantity).label('qty'),
        func.sum(VerdurasMerma.cost_loss).label('loss'),
    ).join(VerdurasProduct,
           VerdurasProduct.id == VerdurasMerma.product_id)
        .filter(
            VerdurasMerma.business_id == business_id,
            VerdurasMerma.registered_at >= start,
            VerdurasMerma.registered_at < end,
        )
        .group_by(VerdurasMerma.product_id, VerdurasProduct.name,
                  VerdurasProduct.unit)
        .order_by(func.sum(VerdurasMerma.cost_loss).desc())
        .all())

    total_loss = sum((Decimal(str(r.loss)) for r in rows),
                     Decimal(0)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    items = []
    for r in rows:
        loss = Decimal(str(r.loss))
        items.append({
            'product_id': r.product_id,
            'name': r.name,
            'unit': r.unit,
            'quantity': str(Decimal(str(r.qty))),
            'cost_loss': str(loss),
            'pct_of_loss': str(
                (loss / total_loss * 100).quantize(
                    Decimal('0.1'), rounding=ROUND_HALF_UP)
            ) if total_loss > 0 else '0.0',
        })

    purchases = db.session.query(
        func.sum(VerdurasLot.total_cost),
    ).filter(
        VerdurasLot.business_id == business_id,
        VerdurasLot.purchased_at >= start,
        VerdurasLot.purchased_at < end,
    ).scalar()
    purchases_cost = Decimal(str(purchases or 0)).quantize(
        _CENTS, rounding=ROUND_HALF_UP)

    return {
        'business_id': business_id,
        'date_from': day_f.isoformat(),
        'date_to': day_t.isoformat(),
        'total_loss': str(total_loss),
        'items': items,
        'purchases_cost': str(purchases_cost),
        'merma_pct_of_purchases': str(
            (total_loss / purchases_cost * 100).quantize(
                Decimal('0.1'), rounding=ROUND_HALF_UP)
        ) if purchases_cost > 0 else None,
    }

"""
Alertas de rotación del vertical Verduras (Semana 5).

Producto: "Te quedan 3kg de banano — considera reponer".

Filosofía (la del módulo, sin excepciones):
- El stock NO se recalcula aquí: se usa EL derivado de
  `services/inventory.py` (compras − ventas − merma). Una sola fuente de
  verdad — si el stock está mal en inventario, está mal en las alertas,
  y arreglarlo es arreglarlo una vez.
- Umbral OPT-IN: solo los productos con `min_stock` configurado generan
  alertas. Sin configuración, cero ruido (el verdulero decide qué vigilar).
- La velocidad de venta (últimos 7 días, ventas no canceladas) da el
  "a este ritmo te dura ~N días" — estimación, no promesa: si no hay
  ventas recientes, la alerta se muestra sin estimación.
- Las alertas INFORMAN, nunca bloquean: el POS las pinta como badges y la
  venta sigue funcionando igual (el stock negativo es visible, no error).
"""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from verduras.models import VerdurasProduct
from verduras.services import inventory as inventory_service
from verduras.services.inventory import (
    VerdurasValidationError,
    _get_product,
)

_MILLIS = Decimal('0.001')

# Ventana de observación de la velocidad de venta (días).
VELOCITY_WINDOW_DAYS = 7


# ── Umbral por producto ─────────────────────────────────────


def set_min_stock(business_id: int, product_id: int, min_stock):
    """Configura (o limpia con None) el umbral de alerta del producto.

    El umbral va en la UNIDAD del producto (5 = 5 kg en un producto kg).
    None = sin alerta (opt-out). Cero se rechaza: si no quieres alerta,
    se quita con None — 0 como umbral no tiene sentido práctico.
    """
    product = _get_product(business_id, product_id)
    if min_stock in (None, ''):
        product.min_stock = None
        db_commit()
        return product
    try:
        qty = Decimal(str(min_stock)).quantize(_MILLIS,
                                               rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(
            f'Umbral inválido: {min_stock!r} (número en {product.unit})')
    if qty < 0:
        raise VerdurasValidationError('El umbral no puede ser negativo')
    if qty == 0:
        raise VerdurasValidationError(
            'Umbral 0 no tiene sentido: usa null para quitar la alerta')
    product.min_stock = qty
    db_commit()
    return product


def db_commit():
    from app.models import db
    db.session.commit()


# ── Velocidad de venta ──────────────────────────────────────


def sales_velocity(business_id: int, product_id: int,
                   days: int = VELOCITY_WINDOW_DAYS) -> Decimal | None:
    """Unidades vendidas por día en los últimos `days` días.

    Reusa la única semántica de "vendido" del inventario (excluye
    canceladas). None si no hubo ventas en la ventana: sin datos no se
    inventa un ritmo.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sold = inventory_service._sum_sales(business_id, product_id, since=since)
    if sold <= 0:
        return None
    return (sold / Decimal(days)).quantize(Decimal('0.01'),
                                           rounding=ROUND_HALF_UP)


# ── Mensajes en lenguaje de verdulero ───────────────────────


def _fmt_qty(value: Decimal) -> str:
    """3.000 → '3' · 2.500 → '2.5' · 0.300 → '0.3' (sin ceros de más)."""
    text = format(value, 'f').rstrip('0').rstrip('.')
    return text or '0'


def _fmt_days(days: Decimal) -> str:
    """~3.0 → '3' · ~1.5 → '1.5' · ~12.3 → '12' (estimación, no precisión)."""
    if days >= 10:
        days = days.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    text = format(days, 'f').rstrip('0').rstrip('.')
    return text or '0'


def _unit_label(unit: str, qty: Decimal) -> str:
    """'unidad' se pluraliza según la cantidad; kg/lb quedan igual."""
    if unit == 'unidad' and qty != 1:
        return 'unidades'
    return unit


def _build_message(name: str, unit: str, stock: Decimal, severity: str,
                   days_left: Decimal | None) -> str:
    if severity == 'out':
        return f'Te quedaste sin {name}. Considera reponer.'
    qty = f'{_fmt_qty(stock)} {_unit_label(unit, stock)}'
    if days_left is not None:
        plural = '' if days_left == 1 else 's'
        return (f'Te quedan {qty} de {name} — a este ritmo te dura '
                f'~{_fmt_days(days_left)} día{plural}. Considera reponer.')
    return f'Te quedan {qty} de {name} — considera reponer.'


# ── Listado de alertas ──────────────────────────────────────


def list_alerts(business_id: int, until=None) -> dict:
    """Alertas activas del negocio (productos con stock <= su umbral).

    Orden: 'out' primero; dentro de cada severidad, los que se agotan
    antes (menos días restantes) primero; sin estimación al final.
    """
    stock_rows = inventory_service.list_stock(business_id, until)
    products = {p.id: p for p in VerdurasProduct.query.filter_by(
        business_id=business_id, is_active=True)}

    alerts = []
    for row in stock_rows:
        product = products.get(row['product_id'])
        if product is None or product.min_stock is None:
            continue
        stock = Decimal(row['stock'])
        threshold = product.min_stock
        if stock > threshold:
            continue
        severity = 'out' if stock <= 0 else 'low'
        velocity = sales_velocity(business_id, product.id)
        days_left = None
        # La estimación de días solo aplica a 'low': un producto agotado
        # no "dura" N días, ya se acabó.
        if severity == 'low' and velocity:
            days_left = (stock / velocity).quantize(
                Decimal('0.1'), rounding=ROUND_HALF_UP)
        alerts.append({
            'product_id': product.id,
            'name': product.name,
            'unit': product.unit,
            'severity': severity,
            'stock': row['stock'],
            'min_stock': str(threshold),
            'velocity_per_day': str(velocity) if velocity else None,
            'days_left': str(days_left) if days_left is not None else None,
            'message': _build_message(product.name, product.unit, stock,
                                      severity, days_left),
        })

    alerts.sort(key=lambda a: (
        0 if a['severity'] == 'out' else 1,
        float(a['days_left']) if a['days_left'] is not None else float('inf'),
        a['name'],
    ))
    return {'alerts': alerts, 'count': len(alerts)}

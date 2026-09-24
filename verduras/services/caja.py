"""
Cierre Z del día del vertical Verduras (sin turnos en v1).

Filosofía (misma del módulo): la DB calcula, el servicio organiza.
- El día operativo es America/Bogota (el mostrador), no UTC.
- El esperado sale de las ventas no canceladas; el contado lo escribe el
  tendero; la diferencia se CALCULA, jamás se edita.
- Un cierre por día y negocio (unique): el duplicado se rechaza, no se
  pisa. Reabrir un día cerrado no existe en v1.
- La ruta de Ventas (/pos/<slug>/ventas) USA estas mismas funciones: el
  resumen que ve el tendero y lo que firma el cierre son el mismo número.

Toda la lógica vive aquí; las rutas solo orquestan (convención del repo).
"""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app.models import db
from verduras.models_sales import VerdurasCierre, VerdurasMovimientoCaja

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python < 3.9 sin tzdata
    ZoneInfo = None

_CENTS = Decimal('0.01')


class CajaValidationError(ValueError):
    """Dato inválido o regla del cierre incumplida."""


def bogota_today():
    """Fecha "hoy" en America/Bogota (el día operativo del mostrador)."""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo('America/Bogota')).date()
        except Exception:  # noqa: BLE001 — tzdata ausente
            pass
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def _local(value):
    """Datetime aware en hora Bogotá (naive → se asume UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if ZoneInfo is None:
        return value - timedelta(hours=5)
    try:
        return value.astimezone(ZoneInfo('America/Bogota'))
    except Exception:  # noqa: BLE001
        return value - timedelta(hours=5)


def _parse_day(value, default_today=True):
    """Normaliza date|string ISO a date (inválido → hoy o None)."""
    if value is None or value == '':
        return bogota_today() if default_today else None
    if hasattr(value, 'isoformat'):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        return bogota_today() if default_today else None


def day_sales(business_id: int, day=None) -> list:
    """Ventas no canceladas del día Bogotá (default: hoy)."""
    from verduras.services import sales as sales_service
    day = _parse_day(day)
    out = []
    for s in sales_service.list_sales(business_id):
        if s.status == 'cancelled' or s.created_at is None:
            continue
        if _local(s.created_at).date() == day:
            out.append(s)
    return out


MOVIMIENTO_TIPOS = ('ingreso', 'retiro')


def registrar_movimiento(business_id: int, tipo: str, monto,
                         motivo=None, day=None) -> VerdurasMovimientoCaja:
    """Asienta un ingreso/retiro de caja del día operativo.

    Monto > 0 siempre (el signo lo pone el tipo). Sin turnos en v1: el
    movimiento suma al esperado del cierre del día.
    """
    tipo = str(tipo or '').strip().lower()
    if tipo not in MOVIMIENTO_TIPOS:
        raise CajaValidationError(
            f"Tipo inválido: '{tipo}'. Válidos: ingreso, retiro")
    try:
        monto = Decimal(str(monto)).quantize(_CENTS)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise CajaValidationError(f'Monto inválido: {monto!r}')
    if monto <= 0:
        raise CajaValidationError('El monto debe ser mayor a 0')
    day = day or bogota_today()
    day = day.isoformat() if hasattr(day, 'isoformat') else str(day)
    mov = VerdurasMovimientoCaja(
        business_id=business_id, day=day, tipo=tipo, monto=monto,
        motivo=(str(motivo or '').strip() or None),
    )
    db.session.add(mov)
    db.session.commit()
    return mov


def movimientos_del_dia(business_id: int, day=None) -> dict:
    """Suma del día por tipo: {'ingreso': X, 'retiro': Y}."""
    day = _parse_day(day)
    day = day.isoformat()
    rows = (VerdurasMovimientoCaja.query.filter_by(
        business_id=business_id, day=day).all())
    totals = {'ingreso': Decimal('0.00'), 'retiro': Decimal('0.00')}
    for r in rows:
        if r.tipo in totals:
            totals[r.tipo] += r.monto
    return totals


def build_close_preview(business_id: int, day=None) -> dict:
    """Resumen computable del día para mostrar ANTES de firmar el cierre.

    Esperado = ventas en efectivo + ingresos − retiros: el mismo número
    que firma close_day (fuente única).
    """
    day = _parse_day(day)
    sales = day_sales(business_id, day)
    total = sum((s.total for s in sales), Decimal('0.00'))
    cash = sum((s.total for s in sales
                if (s.payment_method or '') == 'efectivo'), Decimal('0.00'))
    movs = movimientos_del_dia(business_id, day)
    cash = (cash + movs['ingreso'] - movs['retiro']).quantize(_CENTS)
    by_method = {}
    for s in sales:
        key = s.payment_method or 'sin_registro'
        row = by_method.setdefault(
            key, {'total': Decimal('0.00'), 'count': 0})
        row['total'] += s.total
        row['count'] += 1
    hourly = [Decimal('0.00')] * 24
    for s in sales:
        hourly[_local(s.created_at).hour] += s.total
    return {
        'day': day.isoformat(),
        'tickets': len(sales),
        'total': total,
        'cash_expected': cash,
        'movimientos': movs,
        'by_method': by_method,
        'hourly': hourly,
        'already_closed': (
            VerdurasCierre.query.filter_by(
                business_id=business_id,
                day=day.isoformat()).first() is not None),
    }


def close_day(business_id: int, counted_cash, day=None) -> VerdurasCierre:
    """Firma el Cierre Z del día con el conteo físico del cajón.

    Valida, calcula la diferencia y guarda el snapshot. Duplicado del
    mismo día → error (el cierre no se pisa ni se reabre en v1). Se puede
    firmar un día pasado (ayer se cierra hoy); futuro jamás.
    """
    try:
        counted = Decimal(str(counted_cash)).quantize(_CENTS)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise CajaValidationError(
            f'Efectivo contado inválido: {counted_cash!r}')
    if counted < 0:
        raise CajaValidationError('El contado no puede ser negativo')
    day = _parse_day(day)
    if day > bogota_today():
        raise CajaValidationError('No se puede cerrar un día futuro')
    preview = build_close_preview(business_id, day)
    if preview['already_closed']:
        raise CajaValidationError(
            f'El día {preview["day"]} ya tiene cierre firmado')
    cierre = VerdurasCierre(
        business_id=business_id,
        day=preview['day'],
        total_sales=preview['total'],
        cash_expected=preview['cash_expected'],
        counted_cash=counted,
        difference=(counted - preview['cash_expected']).quantize(_CENTS),
    )
    db.session.add(cierre)
    try:
        db.session.commit()
    except IntegrityError:
        # Carrera: dos cierres simultáneos; el unique frenó al segundo.
        db.session.rollback()
        raise CajaValidationError(
            f'El día {preview["day"]} ya tiene cierre firmado')
    return cierre


def get_cierre(business_id: int, day=None):
    """Cierre firmado del día (o None si el día sigue abierto)."""
    day = _parse_day(day)
    day = day.isoformat()
    return VerdurasCierre.query.filter_by(
        business_id=business_id, day=day).first()


def recent_cierres(business_id: int, limit: int = 7) -> list:
    """Últimos cierres firmados, más nuevos primero (solo lectura)."""
    return (VerdurasCierre.query.filter_by(business_id=business_id)
            .order_by(VerdurasCierre.day.desc(),
                      VerdurasCierre.id.desc())
            .limit(min(int(limit), 31)).all())

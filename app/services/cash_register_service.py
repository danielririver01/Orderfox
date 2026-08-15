"""
CashRegisterService — lógica de negocio del Centro de Caja.

Los totales se basan en `Order.paid_at` (dinero real registrado en caja),
NUNCA en `created_at`. Se excluyen pedidos `cancelled` y pedidos sin pago
(`payment_method IS NULL`).

Rangos de fechas: se resuelven en hora de Colombia (UTC-5) y se convierten a
UTC naive (patrón `today_start_utc`). `end` es SIEMPRE exclusivo.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.models import CashRegister, Order, db
from app.utils.timezone import to_colombia, today_start_utc

PAYMENT_METHODS = ('cash', 'nequi', 'bancolombia', 'card')
RANGE_TYPES = ('today', 'yesterday', 'last_7', 'last_30', 'last_month', 'this_year', 'custom')


def _normalize_methods(method):
    """Normaliza un filtro de método: str | iterable | None → lista de métodos válidos.

    Acepta 'nequi', ['nequi', 'cash'] o ('nequi', 'cash'); descarta valores
    no válidos, None y tipos inesperados.
    """
    if method is None:
        return []
    if isinstance(method, str):
        method = [method]
    elif not isinstance(method, (list, tuple)):
        return []
    return [m for m in method if m in PAYMENT_METHODS]


class NoSalesError(ValueError):
    """Cierre rechazado: el periodo no tiene ventas (total $0)."""

METHOD_LABELS = {
    'cash': 'Efectivo',
    'nequi': 'Nequi',
    'bancolombia': 'Bancolombia',
    'card': 'Tarjeta',
}


class CashRegisterService:
    """Estadísticas y cierres de caja. Compartido por web y API routes."""

    # ── Rangos de fechas ─────────────────────────────────────────────────────

    @staticmethod
    def resolve_range(range_type, from_date=None, to_date=None):
        """Resuelve un rango a (start, end) UTC naive. `end` es exclusivo.

        - today        : [medianoche Bogotá hoy, +1 día)
        - yesterday    : [medianoche Bogotá ayer, medianoche Bogotá hoy)
        - last_7       : [hoy - 6 días, +1 día)  → hoy y los 6 anteriores
        - last_30      : [hoy - 29 días, +1 día) → hoy y los 29 anteriores
        - last_month   : [1° del mes pasado, 1° de este mes)
        - this_year    : [1° de enero, +1 día)
        - custom       : [from_date 00:00 Bogotá, to_date 23:59:59.999 Bogotá)
        """
        now_col = datetime.now(timezone(timedelta(hours=-5)))
        today_start = today_start_utc()  # naive UTC

        if range_type == 'today':
            start = today_start
            end = today_start + timedelta(days=1)
        elif range_type == 'yesterday':
            start = today_start - timedelta(days=1)
            end = today_start
        elif range_type == 'last_7':
            start = today_start - timedelta(days=6)
            end = today_start + timedelta(days=1)
        elif range_type == 'last_30':
            start = today_start - timedelta(days=29)
            end = today_start + timedelta(days=1)
        elif range_type == 'last_month':
            first_this = now_col.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            first_prev = (first_this - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start = first_prev.astimezone(timezone.utc).replace(tzinfo=None)
            end = first_this.astimezone(timezone.utc).replace(tzinfo=None)
        elif range_type == 'this_year':
            start = now_col.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
            end = today_start + timedelta(days=1)
        else:  # custom
            colombia_tz = timezone(timedelta(hours=-5))
            try:
                start_date = date.fromisoformat(from_date) if from_date else None
                end_date = date.fromisoformat(to_date) if to_date else None
            except (TypeError, ValueError):
                raise ValueError('Fechas personalizadas inválidas')
            if not start_date or not end_date:
                raise ValueError('Rango personalizado requiere from y to')
            if end_date < start_date:
                raise ValueError('La fecha final no puede ser anterior a la inicial')
            start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=colombia_tz)
            end_dt = datetime(end_date.year, end_date.month, end_date.day, tzinfo=colombia_tz) + timedelta(days=1)
            start = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
            end = end_dt.astimezone(timezone.utc).replace(tzinfo=None)

        if start >= end:
            raise ValueError('Rango de fechas inválido')
        return start, end

    # ── Resumen del periodo ──────────────────────────────────────────────────

    @staticmethod
    def _paid_base_query(restaurant_id, start, end):
        """Query base: pedidos pagados en [start, end) sin cancelados."""
        return Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status != 'cancelled',
            Order.payment_method.isnot(None),
            Order.paid_at >= start,
            Order.paid_at < end,
        )

    @staticmethod
    def get_summary(restaurant_id, start, end, method=None):
        """Totales y desglose por método de un periodo (basado en paid_at).

        Si `method` es un método válido o una lista de métodos (PAYMENT_METHODS),
        filtra todo el resumen a esos métodos (análisis segmentados del
        Copilot de Caja, p.ej. "solo Nequi" o "Nequi y Efectivo").
        """
        base = CashRegisterService._paid_base_query(restaurant_id, start, end)
        methods = _normalize_methods(method)
        if methods:
            base = base.filter(Order.payment_method.in_(methods))

        total_sales = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
            Order.id.in_(base.with_entities(Order.id))
        ).scalar() or 0

        # Desglose por método en una sola consulta
        rows = db.session.query(
            Order.payment_method,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0),
        ).filter(
            Order.id.in_(base.with_entities(Order.id))
        ).group_by(Order.payment_method).all()

        breakdown = {m: {'total': 0, 'orders': 0} for m in PAYMENT_METHODS}
        for method, count, total in rows:
            if method in breakdown:
                breakdown[method]['total'] = int(total)
                breakdown[method]['orders'] = int(count)

        total_orders = sum(b['orders'] for b in breakdown.values())
        total_sales = int(total_sales)
        avg_ticket = round(total_sales / total_orders) if total_orders else 0

        cash_change = db.session.query(func.coalesce(func.sum(Order.change_due), 0)).filter(
            Order.id.in_(base.with_entities(Order.id)),
            Order.payment_method == 'cash',
        ).scalar() or 0

        return {
            'total_sales': total_sales,
            'total_orders': total_orders,
            'avg_ticket': avg_ticket,
            'breakdown': breakdown,
            'cash_change_total': int(cash_change),
        }

    # ── Pedidos ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_paid_orders(restaurant_id, start, end, method=None, search=None):
        """Pedidos pagados en el periodo, filtrables por método(s) y búsqueda."""
        query = CashRegisterService._paid_base_query(restaurant_id, start, end)

        methods = _normalize_methods(method)
        if methods:
            query = query.filter(Order.payment_method.in_(methods))

        if search:
            like = f'%{search.strip()}%'
            query = query.filter(db.or_(
                Order.order_number.ilike(like),
                Order.customer_name.ilike(like),
                Order.payment_method.ilike(like),
            ))

        orders = query.order_by(Order.paid_at.desc()).all()
        return [
            {
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.customer_name,
                'status': o.status,
                'total': o.total,
                'payment_method': o.payment_method,
                'amount_received': o.amount_received,
                'change_due': o.change_due,
                'paid_at': o.paid_at.isoformat() if o.paid_at else None,
                'created_at': o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]

    @staticmethod
    def get_pending(restaurant_id):
        """Pedidos activos sin pago registrado (pending/confirmed)."""
        orders = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status.in_(['pending', 'confirmed']),
            Order.payment_method.is_(None),
        ).order_by(Order.created_at.asc()).all()

        return [
            {
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.customer_name,
                'status': o.status,
                'total': o.total,
                'created_at': o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]

    # ── Cierres de caja ──────────────────────────────────────────────────────

    @staticmethod
    def _find_overlapping(restaurant_id, start, end):
        """Devuelve cierres previos que se solapan con [start, end)."""
        return CashRegister.query.filter(
            CashRegister.restaurant_id == restaurant_id,
            CashRegister.period_start < end,
            CashRegister.period_end > start,
        ).order_by(CashRegister.period_start.asc()).first()

    @staticmethod
    def close_register(restaurant_id, user_id, start, end):
        """Persiste un cierre de caja para [start, end). Lanza ValueError/409.

        - Rechaza rangos que se solapan con cierres previos (evita contar
          ventas dos veces en el cuadre físico).
        - Rechaza periodos sin ventas (total $0): no tiene sentido cuadrar
          una caja sin movimientos.
        - El unique (restaurant_id, period_start) actúa como red de seguridad
          contra doble clic simultáneo.
        Devuelve el CashRegister creado (tras commit).
        """
        overlap = CashRegisterService._find_overlapping(restaurant_id, start, end)
        if overlap:
            # Mostrar las fechas en hora de Colombia (los rangos se guardan en UTC)
            start_col = to_colombia(overlap.period_start)
            end_col = to_colombia(overlap.period_end)
            fmt = '%d/%m/%Y'
            same_day = start_col.date() == (end_col - timedelta(seconds=1)).date()
            if same_day:
                periodo = start_col.strftime(fmt)
            else:
                periodo = f'{start_col.strftime(fmt)} al {end_col.strftime(fmt)}'
            raise ValueError(
                f'Ya cerraste caja para el periodo {periodo}. '
                f'Este periodo no se puede cerrar dos veces. '
                f'Revisa el historial de cierres si necesitas el ticket.'
            )

        summary = CashRegisterService.get_summary(restaurant_id, start, end)
        if summary['total_sales'] == 0:
            raise NoSalesError(
                'No hay ventas en este periodo, no puedes cerrar caja. '
                'Verifica el rango de fechas o registra pagos primero.'
            )
        b = summary['breakdown']

        closing = CashRegister(
            restaurant_id=restaurant_id,
            closed_by=user_id,
            period_start=start,
            period_end=end,
            total_sales=summary['total_sales'],
            total_orders=summary['total_orders'],
            avg_ticket=summary['avg_ticket'],
            cash_total=b['cash']['total'],
            cash_orders=b['cash']['orders'],
            nequi_total=b['nequi']['total'],
            nequi_orders=b['nequi']['orders'],
            bancolombia_total=b['bancolombia']['total'],
            bancolombia_orders=b['bancolombia']['orders'],
            card_total=b['card']['total'],
            card_orders=b['card']['orders'],
            cash_change_total=summary['cash_change_total'],
        )
        db.session.add(closing)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ValueError(
                'Ya existe un cierre para este periodo. '
                'Revisa el historial de cierres antes de intentar de nuevo.'
            )
        return closing

    @staticmethod
    def get_closes(restaurant_id, limit=30):
        """Cierres más recientes del restaurante (para el historial)."""
        closes = CashRegister.query.filter_by(restaurant_id=restaurant_id) \
            .order_by(CashRegister.created_at.desc()).limit(limit).all()
        return [
            {
                'id': c.id,
                'period_start': c.period_start.isoformat() if c.period_start else None,
                'period_end': c.period_end.isoformat() if c.period_end else None,
                'total_sales': c.total_sales,
                'total_orders': c.total_orders,
                'avg_ticket': c.avg_ticket,
                'cash_total': c.cash_total,
                'cash_change_total': c.cash_change_total,
                'created_at': c.created_at.isoformat() if c.created_at else None,
                'closed_by': c.closed_by_user.username if c.closed_by_user else None,
            }
            for c in closes
        ]

    @staticmethod
    def get_close(restaurant_id, close_id):
        """Un cierre por ID, verificado por restaurante (anti-IDOR)."""
        return CashRegister.query.filter_by(
            id=close_id, restaurant_id=restaurant_id).first()

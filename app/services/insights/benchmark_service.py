"""
Benchmarking anónimo de la plataforma para Copilot VZ (Fase 1).

Calcula agregados estadísticos (MEDIANAS) sobre todos los restaurantes
activos de Velzia y los guarda como snapshots en platform_benchmarks.

Privacidad (k-anonymity):
- Una cohorte solo se publica si tiene >= K_MIN restaurantes con datos
  suficientes en la ventana de análisis.
- Se usan MEDIANAS, nunca promedios ni filas crudas: un restaurante atípico
  no distorsiona el valor publicado ni permite inferir el dato de un
  competidor individual.
- Cohortes: 'global' + una por cuisine_type (ej. 'hamburguesas').

El LLM recibe estos valores como "benchmarks de la plataforma" para comparar
el negocio del usuario contra pares anónimos. Si la cohorte del restaurante
no alcanza el mínimo, se usa 'global'; si tampoco existe, no se envía nada
y el system prompt prohíbe inventar comparativos.
"""

import json
import statistics
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from app import db
from app.models import Order, OrderItem, Restaurant
from app.models.ai import PlatformBenchmark

# k-anonymity mínimo por cohorte (incluye 'global').
K_MIN = 5
# Ventana de cálculo en días.
PERIOD_DAYS = 30
# Pedidos mínimos por restaurante en la ventana para incluirlo en la cohorte.
MIN_ORDERS_PER_RESTAURANT = 10


def _to_date(d):
    """
    Normaliza el resultado de func.date() a datetime.date.
    MySQL (pymysql) devuelve date; SQLite devuelve str 'YYYY-MM-DD'.
    """
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def _median(values, ndigits=2):
    """Mediana robusta; None si no hay datos."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(float(statistics.median(vals)), ndigits)


def _compute_restaurant_metrics(restaurant_id, daily_rows, top_product_rows):
    """
    Métricas individuales de UN restaurante a partir de filas ya agregadas.

    daily_rows: [(date, total, orders), ...] últimos PERIOD_DAYS días.
    top_product_rows: [(product_name, revenue), ...] misma ventana.
    """
    if not daily_rows:
        return None

    total_revenue = sum(r[1] for r in daily_rows)
    total_orders = sum(r[2] for r in daily_rows)
    if total_orders < MIN_ORDERS_PER_RESTAURANT or total_revenue <= 0:
        return None

    avg_ticket = total_revenue / total_orders
    # Semanas cubiertas: span real entre primera y última venta con venta,
    # con piso de 7 días para restaurantes nuevos.
    dates = sorted(_to_date(r[0]) for r in daily_rows)
    span_days = max((dates[-1] - dates[0]).days + 1, 7)
    orders_per_week = total_orders / (span_days / 7)

    # Distribución de ventas por día de semana (share 0..1), 0=lunes..6=domingo.
    weekday_share = {str(i): 0.0 for i in range(7)}
    for d, t, _o in daily_rows:
        idx = _to_date(d).weekday()
        weekday_share[str(idx)] += t
    if total_revenue > 0:
        weekday_share = {k: round(v / total_revenue, 4) for k, v in weekday_share.items()}

    # Concentración de ingresos en el top 3 de productos.
    product_revenue = [rev for _name, rev in top_product_rows]
    items_total = sum(product_revenue)
    top3_share = (sum(sorted(product_revenue, reverse=True)[:3]) / items_total) if items_total > 0 else None

    return {
        'restaurant_id': restaurant_id,
        'avg_ticket': avg_ticket,
        'orders_per_week': orders_per_week,
        'weekday_share': weekday_share,
        'top3_share': top3_share,
        '_total_revenue': total_revenue,
    }


def _mom_growth_for(rows_by_restaurant, start, end_prev, end_cur):
    """
    Crecimiento % mes a mes por restaurante:
    (revenue ventana actual - revenue ventana previa) / previa.
    Solo si la ventana previa tiene ventas (> 0).
    rows_by_restaurant: {rid: revenue_actual}
    """
    prev_rows = db.session.query(
        Order.restaurant_id,
        func.coalesce(func.sum(Order.total), 0),
    ).filter(
        Order.status != 'cancelled',
        func.date(Order.created_at) >= end_prev,
        func.date(Order.created_at) < start,
    ).group_by(Order.restaurant_id).all()

    prev_map = {r[0]: float(r[1] or 0) for r in prev_rows}
    growth = {}
    for rid, cur in rows_by_restaurant.items():
        prev = prev_map.get(rid)
        if prev and prev > 0:
            growth[rid] = ((cur - prev) / prev)
    return growth


def compute_benchmarks():
    """
    Recalcula los snapshots de benchmarks ('global' + cohortes por cuisine_type).
    Reemplaza el snapshot anterior de cada cohorte (siempre queda 1 fila/cohort).
    Retorna {'cohorts': N, 'restaurants': M} o {'cohorts': 0} si no hay datos.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    start_date = today - timedelta(days=PERIOD_DAYS)

    # Restaurantes activos candidatos (solo activos + que participen en benchmarking).
    active_ids = [r[0] for r in db.session.query(Restaurant.id).filter(
        Restaurant.is_active == True,
        Restaurant.allow_benchmark == True,
    ).all()]
    if not active_ids:
        return {'cohorts': 0}

    # Ventana actual agregada por restaurante/día.
    daily = db.session.query(
        Order.restaurant_id,
        func.date(Order.created_at),
        func.coalesce(func.sum(Order.total), 0),
        func.count(Order.id),
    ).filter(
        Order.restaurant_id.in_(active_ids),
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start_date,
    ).group_by(Order.restaurant_id, func.date(Order.created_at)).all()

    daily_by_rid = {}
    for rid, d, total, orders in daily:
        daily_by_rid.setdefault(rid, []).append((d, float(total or 0), int(orders)))

    # Top productos por restaurante (ingresos) en la misma ventana.
    top_products = db.session.query(
        OrderItem.restaurant_id,
        OrderItem.product_name,
        func.coalesce(func.sum(OrderItem.subtotal), 0),
    ).join(Order, Order.id == OrderItem.order_id).filter(
        OrderItem.restaurant_id.in_(active_ids),
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start_date,
    ).group_by(OrderItem.restaurant_id, OrderItem.product_name).all()

    products_by_rid = {}
    for rid, name, rev in top_products:
        products_by_rid.setdefault(rid, []).append((name, float(rev or 0)))

    # Métricas individuales + crecimiento MoM.
    per_restaurant = {}
    for rid in active_ids:
        m = _compute_restaurant_metrics(rid, daily_by_rid.get(rid, []), products_by_rid.get(rid, []))
        if m:
            per_restaurant[rid] = m

    if len(per_restaurant) < K_MIN:
        # Aún sin volumen suficiente: limpiar snapshots viejos y salir.
        PlatformBenchmark.query.delete()
        db.session.commit()
        return {'cohorts': 0, 'reason': 'insufficient_restaurants',
                'qualifying': len(per_restaurant)}

    revenue_by_rid = {rid: m.pop('_total_revenue') for rid, m in per_restaurant.items()}
    mom_growth = _mom_growth_for(revenue_by_rid, start_date,
                                 start_date - timedelta(days=PERIOD_DAYS), start_date)

    cuisine_by_rid = dict(db.session.query(Restaurant.id, Restaurant.cuisine_type).filter(
        Restaurant.id.in_(list(per_restaurant.keys()))
    ).all())

    def _cohort_snapshot(rows):
        weekday = {str(i): _median([r['weekday_share'].get(str(i)) for r in rows], 4)
                   for i in range(7)}
        shares = [r['top3_share'] for r in rows if r['top3_share'] is not None]
        return {
            'avg_ticket_cop': _median([r['avg_ticket'] for r in rows], 0),
            'orders_per_week': _median([r['orders_per_week'] for r in rows], 1),
            'top3_revenue_share': _median(shares, 4),
            'mom_growth_pct': _median([mom_growth.get(r['restaurant_id']) for r in rows], 4),
            'weekday_sales_share': weekday,
        }

    cohorts = {'global': list(per_restaurant.values())}
    for rid, m in per_restaurant.items():
        cohorts.setdefault(cuisine_by_rid.get(rid, 'general'), []).append(m)

    written = 0
    for cohort_name, rows in cohorts.items():
        if len(rows) < K_MIN:
            continue  # k-anonymity: cohorte demasiado pequeña, no se publica
        snapshot = _cohort_snapshot(rows)
        existing = PlatformBenchmark.query.filter_by(cohort=cohort_name).first()
        if existing:
            existing.restaurant_count = len(rows)
            existing.period_days = PERIOD_DAYS
            existing.metrics_json = json.dumps(snapshot)
            existing.computed_at = now
        else:
            db.session.add(PlatformBenchmark(
                cohort=cohort_name,
                restaurant_count=len(rows),
                period_days=PERIOD_DAYS,
                metrics_json=json.dumps(snapshot),
                computed_at=now,
            ))
        written += 1

    db.session.commit()
    return {'cohorts': written, 'qualifying': len(per_restaurant)}


def get_benchmark_for(restaurant):
    """
    Mejor snapshot disponible para un restaurante:
    primero su cuisine_type, luego 'global'. None si no hay nada publicado.
    """
    if restaurant is None:
        return None
    row = PlatformBenchmark.query.filter_by(cohort=restaurant.cuisine_type or 'general').first()
    if not row:
        row = PlatformBenchmark.query.filter_by(cohort='global').first()
    return row


def benchmarks_for_context(restaurant):
    """
    Payload compacto para inyectar en build_context(). Devuelve None cuando
    no hay benchmark publicado o el restaurante optó por no participar.
    """
    if restaurant is None or not restaurant.allow_benchmark:
        return None
    row = get_benchmark_for(restaurant)
    if not row:
        return None
    return {
        'source': 'plataforma_velzia_anonimizado',
        'cohort': row.cohort,
        'cohort_size': row.restaurant_count,
        'period_days': row.period_days,
        **row.metrics,
    }

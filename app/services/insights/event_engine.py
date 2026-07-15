"""
event_engine.py — Detección automática de BusinessEvents para Copilot VZ.

"El sistema detecta. Copilot interpreta."

PostgreSQL descubre el evento, Flask lo organiza en un BusinessEvent,
y Copilot lo presenta al usuario con un template (sin LLM). Solo si el
usuario hace clic en "Analizar" se consume un crédito de DeepSeek.

Prioridades:
  100 = primera_venta  (una vez en la vida del restaurante)
  90  = caida_fuerte
  80  = stock_critico
  70  = record_semanal
  60  = nuevo_top_producto
  40  = recomendacion
"""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import func

from app import db
from app.models import Restaurant, Order, OrderItem, Product, CopilotBusinessEvent
from app.services.insights.event_templates import TEMPLATES, KIND_PRIORITY, KIND_COOLDOWN


def _now():
    return datetime.now(timezone.utc)


def _today():
    return _now().date()


def _active_event_exists(restaurant_id):
    """True si ya hay un evento activo para este restaurante."""
    return db.session.query(
        CopilotBusinessEvent.query.filter(
            CopilotBusinessEvent.restaurant_id == restaurant_id,
            CopilotBusinessEvent.active == True,
        ).exists()
    ).scalar()


def _has_recent_event(restaurant_id, kind, cooldown_days):
    """True si ya hubo un evento del mismo tipo dentro del cooldown."""
    if cooldown_days is None:
        return False  # Sin cooldown (ej: first_sales solo una vez)
    cutoff = _now() - timedelta(days=cooldown_days)
    return db.session.query(
        CopilotBusinessEvent.query.filter(
            CopilotBusinessEvent.restaurant_id == restaurant_id,
            CopilotBusinessEvent.kind == kind,
            CopilotBusinessEvent.created_at >= cutoff,
        ).exists()
    ).scalar()


def _has_any_first_sales_event(restaurant_id):
    """True si ya se generó un evento first_sales para este restaurante."""
    return db.session.query(
        CopilotBusinessEvent.query.filter(
            CopilotBusinessEvent.restaurant_id == restaurant_id,
            CopilotBusinessEvent.kind == 'first_sales',
        ).exists()
    ).scalar()


def _has_any_event_of_kind(restaurant_id, kind):
    """True si ya se generó alguna vez este tipo de evento."""
    return db.session.query(
        CopilotBusinessEvent.query.filter(
            CopilotBusinessEvent.restaurant_id == restaurant_id,
            CopilotBusinessEvent.kind == kind,
        ).exists()
    ).scalar()


def _week_range():
    """Retorna (lunes, domingo) de la semana actual."""
    today = _today()
    monday = today - timedelta(days=today.weekday())
    return monday, today


def _prev_week_range():
    """Retorna (lunes, domingo) de la semana anterior."""
    today = _today()
    end = today - timedelta(days=today.weekday() + 1)
    start = end - timedelta(days=6)
    return start, end


def _week_revenue(restaurant_id, start, end):
    """Suma de ingresos en un rango de fechas."""
    row = db.session.query(
        func.coalesce(func.sum(Order.total), 0)
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start,
        func.date(Order.created_at) <= end,
    ).first()
    return int(row[0] or 0)


def _total_order_count(restaurant_id):
    """Cantidad total de órdenes no canceladas."""
    return db.session.query(func.count(Order.id)).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
    ).scalar() or 0


def _product_count(restaurant_id):
    """Cantidad de productos activos."""
    return db.session.query(func.count(Product.id)).filter(
        Product.restaurant_id == restaurant_id,
        Product.is_active == True,
    ).scalar() or 0


def _top_product_last_30d(restaurant_id):
    """Retorna (nombre, cantidad) del producto más vendido en los últimos 30 días."""
    cutoff = _today() - timedelta(days=30)
    row = db.session.query(
        OrderItem.product_name,
        func.sum(OrderItem.quantity),
    ).join(Order).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= cutoff,
    ).group_by(OrderItem.product_name).order_by(
        func.sum(OrderItem.quantity).desc()
    ).first()
    if row:
        return str(row[0]), int(row[1])
    return None, 0


def _second_top_product_last_30d(restaurant_id):
    """Retorna nombre del segundo producto más vendido."""
    cutoff = _today() - timedelta(days=30)
    row = db.session.query(
        OrderItem.product_name,
        func.sum(OrderItem.quantity),
    ).join(Order).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= cutoff,
    ).group_by(OrderItem.product_name).order_by(
        func.sum(OrderItem.quantity).desc()
    ).offset(1).first()
    if row:
        return str(row[0])
    return None


def _save_event(restaurant_id, kind, title, preview, template_key, template_data=None):
    """Crea un BusinessEvent en BD."""
    priority = KIND_PRIORITY.get(kind, 0)
    ev = CopilotBusinessEvent(
        restaurant_id=restaurant_id,
        kind=kind,
        priority=priority,
        title=title,
        preview=preview,
        template_key=template_key,
        template_data=json.dumps(template_data, ensure_ascii=False) if template_data else None,
    )
    db.session.add(ev)
    db.session.commit()
    return ev


def check_first_sales(restaurant_id):
    """Busca restaurantes que acaban de alcanzar nivel 3 (primeras ventas)."""
    if _has_any_first_sales_event(restaurant_id):
        return None
    if _active_event_exists(restaurant_id):
        return None
    order_count = _total_order_count(restaurant_id)
    product_count = _product_count(restaurant_id)
    if order_count >= 1 and product_count >= 1:
        tpl = TEMPLATES['first_sales']
        return _save_event(
            restaurant_id=restaurant_id,
            kind='first_sales',
            title=tpl['title'],
            preview='Ya tengo suficientes datos para analizar tu negocio. ¿Quieres verlo?',
            template_key='first_sales',
        )
    return None


def check_record_week(restaurant_id):
    """Detecta si la semana actual es récord vs. el promedio histórico."""
    if _has_recent_event(restaurant_id, 'record_week', KIND_COOLDOWN.get('record_week', 30)):
        return None
    if _active_event_exists(restaurant_id):
        return None
    mon, today = _week_range()
    if today - mon < timedelta(days=3):
        return None  # Muy temprano en la semana, no confiable
    current = _week_revenue(restaurant_id, mon, today)
    if current == 0:
        return None
    # Promedio de semanas anteriores (hasta 8 semanas atrás)
    avg = 0
    count = 0
    for i in range(1, 9):
        ps, pe = _prev_week_range()
        # Desplazar i semanas atrás
        ps -= timedelta(weeks=i - 1)
        pe -= timedelta(weeks=i - 1)
        r = _week_revenue(restaurant_id, ps, pe)
        if r > 0:
            avg += r
            count += 1
    if count == 0:
        return None
    avg_rev = avg / count
    if avg_rev == 0:
        return None
    pct = round(((current - avg_rev) / avg_rev) * 100)
    if pct >= 20:
        tpl = TEMPLATES['record_week']
        return _save_event(
            restaurant_id=restaurant_id,
            kind='record_week',
            title=tpl['title'],
            preview=f'Ventas +{pct}% vs. tu promedio semanal.',
            template_key='record_week',
            template_data={'revenue': f'${current:,}', 'pct': pct},
        )
    return None


def check_big_drop(restaurant_id):
    """Detecta si las ventas cayeron >= 30% vs. la semana anterior."""
    if _has_recent_event(restaurant_id, 'big_drop', KIND_COOLDOWN.get('big_drop', 7)):
        return None
    if _active_event_exists(restaurant_id):
        return None
    mon, today = _week_range()
    if today - mon < timedelta(days=2):
        return None
    current = _week_revenue(restaurant_id, mon, today)
    if current == 0:
        return None
    prev_start = mon - timedelta(days=7)
    prev_end = today - timedelta(days=7)
    previous = _week_revenue(restaurant_id, prev_start, prev_end)
    if previous == 0:
        return None
    pct = round(((current - previous) / previous) * 100)
    if pct <= -30:
        tpl = TEMPLATES['big_drop']
        return _save_event(
            restaurant_id=restaurant_id,
            kind='big_drop',
            title=tpl['title'],
            preview=f'Ventas {pct}% vs. la semana anterior.',
            template_key='big_drop',
            template_data={'revenue': f'${current:,}', 'pct': abs(pct)},
        )
    return None


def check_top_product_change(restaurant_id):
    """Detecta si hay un nuevo producto más vendido."""
    if _has_recent_event(restaurant_id, 'top_product_new', KIND_COOLDOWN.get('top_product_new', 30)):
        return None
    if _active_event_exists(restaurant_id):
        return None
    current_top, _ = _top_product_last_30d(restaurant_id)
    if not current_top:
        return None
    # Buscar si ya se registró este producto como top anteriormente
    existing = db.session.query(
        CopilotBusinessEvent.query.filter(
            CopilotBusinessEvent.restaurant_id == restaurant_id,
            CopilotBusinessEvent.kind == 'top_product_new',
            CopilotBusinessEvent.active == False,
        ).exists()
    ).scalar()
    if not existing:
        return None  # Sin historial, no podemos detectar cambio
    previous_top = _second_top_product_last_30d(restaurant_id)
    if not previous_top:
        return None
    tpl = TEMPLATES['top_product_new']
    return _save_event(
        restaurant_id=restaurant_id,
        kind='top_product_new',
        title=tpl['title'],
        preview=f'{current_top} es ahora tu producto más vendido.',
        template_key='top_product_new',
        template_data={'product': current_top, 'previous': previous_top},
    )


def scan_restaurant(restaurant_id):
    """Ejecuta todas las detecciones para un restaurante.

    Retorna el evento creado o None.
    Se detiene en el primer evento encontrado (máximo 1 activo).
    """
    checks = [
        check_first_sales,
        check_big_drop,
        check_record_week,
        check_top_product_change,
    ]
    for check in checks:
        ev = check(restaurant_id)
        if ev:
            return ev
    return None


def scan_all_restaurants():
    """Escanea todos los restaurantes con datos suficientes. Para APScheduler."""
    restaurants = Restaurant.query.filter(
        Restaurant.is_active == True,
    ).all()
    results = {'scanned': 0, 'events_created': 0}
    for r in restaurants:
        ev = scan_restaurant(r.id)
        results['scanned'] += 1
        if ev:
            results['events_created'] += 1
    return results


def get_pending_event(restaurant_id):
    """Retorna el evento activo más prioritario, o None."""
    return CopilotBusinessEvent.query.filter(
        CopilotBusinessEvent.restaurant_id == restaurant_id,
        CopilotBusinessEvent.active == True,
    ).order_by(
        CopilotBusinessEvent.priority.desc(),
        CopilotBusinessEvent.created_at.desc(),
    ).first()


def auto_dismiss_expired():
    """Marca como inactivos eventos activos con más de 7 días."""
    cutoff = _now() - timedelta(days=7)
    expired = CopilotBusinessEvent.query.filter(
        CopilotBusinessEvent.active == True,
        CopilotBusinessEvent.created_at < cutoff,
        CopilotBusinessEvent.kind != 'first_sales',  # first_sales nunca expira
    ).all()
    for ev in expired:
        ev.active = False
        ev.dismissed_at = _now()
    if expired:
        db.session.commit()
    return len(expired)

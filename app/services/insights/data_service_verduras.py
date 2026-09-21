"""
data_service_verduras.py — Capa de datos de Copilot VZ para el vertical Verduras.

FASE 0 (Ventas): el mismo cerebro, otro adapter. Misma filosofía que
data_service.py — la DB calcula, Flask organiza, la IA interpreta — y la
MISMA interfaz (nombres de función y formas de respuesta) para que el
message_handler opere con cualquier vertical sin ramas por todos lados:
tenant_router elige el módulo según el tenant de la conversación.

Diferencias con restaurante:
- Tenant = business_id (tabla businesses, vertical='verduras'), NO restaurant_id.
- Ventas = VerdurasSale / VerdurasSaleItem (cantidades en kg/lb/unidad,
  con snapshot contable de nombre/unidad/precio por línea).
- Catálogo = VerdurasProduct (+ VerdurasPriceHistory como serie de precios).
- Portabilidad: SIN extract('dow') ni funciones específicas de motor.
  Se agrega con func.date() y el día de semana se calcula en Python, así
  funciona igual en PostgreSQL (prod) y SQLite (tests).

FASE 1 (inventario, merma, rentabilidad, reposición): lee los MODELOS
(verduras_lots, verduras_merma — tablas compartidas, contrato estable), NO el
service del módulo (interno del vertical, debe poder extraerse sin romper a
core). Fórmulas idénticas a verduras/services/inventory.py: stock = compras
− ventas − merma; costo = promedio ponderado por cantidad; pérdida de merma
= snapshot congelado en COP. Sin lotes de un producto no hay costo ni margen:
se reporta sin_datos, jamás se inventa.
"""

import random
from datetime import date as _date
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import func

from app import db
from app.models import Business
from verduras.models import VerdurasCategory, VerdurasProduct
from verduras.models_inventory import VerdurasLot, VerdurasMerma
from verduras.models_sales import VerdurasSale, VerdurasSaleItem


# ── Ventana de contexto por modo (igual que data_service) ────────────────────
DEPTH_DAYS = {'fast': 7, 'normal': 60, 'detailed': 90}


def _today_utc():
    return datetime.now(timezone.utc).date()


def _num(value, default=0):
    """int/float tolerante a None, Decimal y str (Numeric en SQLite/PG)."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_date(value):
    """func.date() devuelve date en PG/MySQL pero str en SQLite: normalizar."""
    if value is None:
        return None
    if isinstance(value, _date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return _date.fromisoformat(str(value)[:10])


def _cop(amount):
    """Formato COP con punto de miles (mismo estilo que data_service)."""
    return '{:,}'.format(int(amount)).replace(',', '.')


def _sales_base(business_id):
    """Ventas del business excluyendo canceladas (pending + completed cuentan)."""
    return VerdurasSale.query.filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
    )


def _range_summary(business_id, start, end):
    """Suma total, nº ventas y ticket promedio en [start, end] (UTC).

    Claves idénticas a data_service (_range_summary): total/orders/avg_ticket.
    """
    rows = db.session.query(
        func.coalesce(func.sum(VerdurasSale.total), 0),
        func.count(VerdurasSale.id),
    ).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= start,
        func.date(VerdurasSale.created_at) <= end,
    ).first()
    total = int(_num(rows[0]))
    sales = int(_num(rows[1]))
    avg = round(total / sales) if sales else 0
    return {'total': total, 'orders': sales, 'avg_ticket': avg}


def _kg_in_range(business_id, start, end):
    """Kilos vendidos en el rango (solo líneas en kg; lb/unidad no se mezclan)."""
    rows = db.session.query(
        func.coalesce(func.sum(VerdurasSaleItem.quantity), 0),
    ).join(VerdurasSale, VerdurasSale.id == VerdurasSaleItem.sale_id).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        VerdurasSaleItem.unit == 'kg',
        func.date(VerdurasSale.created_at) >= start,
        func.date(VerdurasSale.created_at) <= end,
    ).first()
    return round(_num(rows[0]), 3)


def sales_for_date(business_id, days_ago=0):
    base = _today_utc() - timedelta(days=days_ago)
    s = _range_summary(business_id, base, base)
    kg = _kg_in_range(business_id, base, base)
    label = 'hoy' if days_ago == 0 else ('ayer' if days_ago == 1 else f'hace {days_ago} días')
    day = 'Hoy' if days_ago == 0 else 'Ayer'
    avg_txt = f". Ticket promedio: ${_cop(s['avg_ticket'])}" if s['orders'] else ''
    kg_txt = f" ({kg:g} kg)" if kg else ''
    return {
        'text': (
            f"{day} vendiste ${_cop(s['total'])} COP "
            f"en {s['orders']} ventas{kg_txt}{avg_txt}."
        ),
        'summary': s,
        'label': label,
    }


def top_products(business_id, days=30, limit=5):
    """Top por ingresos; qty en la unidad dominante del producto (casi siempre kg)."""
    since = _today_utc() - timedelta(days=days)
    rows = db.session.query(
        VerdurasSaleItem.product_name,
        func.sum(VerdurasSaleItem.quantity).label('qty'),
        func.sum(VerdurasSaleItem.line_total).label('rev'),
    ).join(VerdurasSale, VerdurasSale.id == VerdurasSaleItem.sale_id).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= since,
    ).group_by(VerdurasSaleItem.product_name).order_by(
        func.sum(VerdurasSaleItem.line_total).desc()).limit(limit).all()
    if not rows:
        return {'text': 'Aún no tienes ventas registradas en este período.', 'items': []}
    units = db.session.query(
        VerdurasSaleItem.product_name,
        VerdurasSaleItem.unit,
        func.count(VerdurasSaleItem.id).label('n'),
    ).join(VerdurasSale, VerdurasSale.id == VerdurasSaleItem.sale_id).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= since,
    ).group_by(VerdurasSaleItem.product_name, VerdurasSaleItem.unit).all()
    best_unit = {}
    for r in units:
        if r.product_name not in best_unit or r.n > best_unit[r.product_name][1]:
            best_unit[r.product_name] = (r.unit, r.n)
    items = [{
        'name': r.product_name,
        'qty': round(_num(r.qty), 3),
        'unit': (best_unit.get(r.product_name) or ('kg', 0))[0],
        'revenue': int(_num(r.rev)),
    } for r in rows]
    lines = '\n'.join(
        f"{i + 1}. {it['name']} — ${_cop(it['revenue'])} COP ({it['qty']:g} {it['unit']})"
        for i, it in enumerate(items)
    )
    return {'text': 'Productos más vendidos (por ingresos):\n' + lines, 'items': items}


def avg_ticket(business_id, days=30):
    s = _range_summary(business_id, _today_utc() - timedelta(days=days), _today_utc())
    return {
        'text': (
            f"Tu ticket promedio es ${_cop(s['avg_ticket'])} COP "
            f"({s['orders']} ventas en los últimos {days} días)."
        ),
        'summary': s,
    }


def new_customers(business_id, days_ago=0):
    """Teléfonos distintos con venta ese día (vacios excluidos: default '')."""
    base = _today_utc() - timedelta(days=days_ago)
    count = db.session.query(func.count(func.distinct(VerdurasSale.customer_phone))).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) == base,
        VerdurasSale.customer_phone.isnot(None),
        VerdurasSale.customer_phone != '',
    ).scalar() or 0
    label = 'hoy' if days_ago == 0 else ('ayer' if days_ago == 1 else f'hace {days_ago} días')
    return {'text': f"Tuviste {count} cliente(s) nuevo(s) {label}.", 'count': int(count)}


def compare_months(business_id):
    today = _today_utc()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    cur = _range_summary(business_id, first_this, today)
    prev = _range_summary(business_id, first_prev, last_prev)
    if prev['total'] > 0:
        pct = round(((cur['total'] - prev['total']) / prev['total']) * 100, 1)
        trend_txt = f" ({pct:+}% vs mes anterior)"
    else:
        trend_txt = ' (mes anterior sin ventas)'
    text = (
        f"Este mes llevas ${_cop(cur['total'])} COP en {cur['orders']} ventas.\n"
        f"Mes anterior: ${_cop(prev['total'])} COP en {prev['orders']} ventas{trend_txt}."
    )
    return {'text': text, 'current': cur, 'previous': prev}


def sales_window(business_id, days=7):
    s = _range_summary(business_id, _today_utc() - timedelta(days=days), _today_utc())
    kg = _kg_in_range(business_id, _today_utc() - timedelta(days=days), _today_utc())
    label = 'esta semana' if days <= 7 else f'los últimos {days} días'
    kg_txt = f" ({kg:g} kg)" if kg else ''
    return {
        'text': f"Ventas de {label}: ${_cop(s['total'])} COP en {s['orders']} ventas{kg_txt}.",
        'summary': s,
    }


# ── Despacho de consultas rápidas (Nivel 1, mismos intents que restaurante) ───

def handle_quick(business_id, intent):
    if intent == 'sales_today':
        return sales_for_date(business_id, 0)
    if intent == 'sales_yesterday':
        return sales_for_date(business_id, 1)
    if intent == 'orders_today':
        s = _range_summary(business_id, _today_utc(), _today_utc())
        return {'text': f"Tuviste {s['orders']} ventas hoy.", 'summary': s}
    if intent == 'top_product':
        return top_products(business_id, 30, 5)
    if intent == 'avg_ticket':
        return avg_ticket(business_id, 30)
    if intent == 'new_customers':
        return new_customers(business_id, 0)
    if intent == 'compare_months':
        return compare_months(business_id)
    if intent == 'week_sales':
        return sales_window(business_id, 7)
    if intent == 'month_sales':
        return sales_window(business_id, 30)
    if intent == 'stock_status':
        return stock_status(business_id)
    if intent == 'merma_month':
        return merma_month(business_id)
    return sales_for_date(business_id, 0)


# ── Contexto enriquecido para el LLM (Nivel 2) ───────────────────────────────

def daily_series_since(business_id, start):
    """[(date, total), ...] por día desde start hasta hoy (fechas normalizadas)."""
    rows = db.session.query(
        func.date(VerdurasSale.created_at).label('d'),
        func.coalesce(func.sum(VerdurasSale.total), 0).label('total'),
    ).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= start,
    ).group_by(func.date(VerdurasSale.created_at)).order_by(
        func.date(VerdurasSale.created_at)).all()
    return [(_as_date(r.d), int(_num(r.total))) for r in rows]


def build_context(business_id, days=60, include_catalog=False, depth='normal'):
    """Dict YA procesado para el LLM. Mismas claves que data_service.build_context.

    Extra verdulería: 'vertical' = 'verduras' y nota de unidades, para que el
    prompt_builder active la sección del vertical (precios por kg, cantidades
    fraccionadas). Sin stock/costos: el LLM no debe inventarlos (FASE 1).
    """
    days = DEPTH_DAYS.get(depth, days)
    today = _today_utc()
    start = today - timedelta(days=days)

    series = daily_series_since(business_id, start)
    daily = [{'date': str(d), 'total': t, 'orders': 0} for d, t in series]
    counts = db.session.query(
        func.date(VerdurasSale.created_at).label('d'),
        func.count(VerdurasSale.id).label('n'),
    ).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= start,
    ).group_by(func.date(VerdurasSale.created_at)).all()
    by_day = {str(_as_date(r.d)): int(_num(r.n)) for r in counts}
    for row in daily:
        row['orders'] = by_day.get(row['date'], 0)

    overall = _range_summary(business_id, start, today)

    top_rev = top_products(business_id, days, 8)['items']
    top_qty_rows = db.session.query(
        VerdurasSaleItem.product_name,
        func.sum(VerdurasSaleItem.quantity).label('qty'),
    ).join(VerdurasSale, VerdurasSale.id == VerdurasSaleItem.sale_id).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= start,
    ).group_by(VerdurasSaleItem.product_name).order_by(
        func.sum(VerdurasSaleItem.quantity).desc()).limit(8).all()
    top_qty = [{'name': r.product_name, 'qty': round(_num(r.qty), 3)} for r in top_qty_rows]

    catalog_details = []
    if include_catalog:
        products = db.session.query(VerdurasProduct).filter(
            VerdurasProduct.business_id == business_id,
        ).order_by(VerdurasProduct.name).all()
        for p in products:
            catalog_details.append({
                'id': p.id,
                'name': p.name,
                'price': float(p.current_price) if p.current_price else 0,
                'unit': p.unit,
                'category': p.category.name if p.category else None,
                'is_active': bool(p.is_active),
                'created_at': str(p.created_at.date()) if p.created_at else None,
            })

    # Ventas por día de semana (0=lunes..6=domingo), calculado en Python.
    weekday = {i: 0 for i in range(7)}
    for d, t in series:
        if d is not None:
            weekday[d.weekday()] += t

    catalog = db.session.query(
        func.count(VerdurasProduct.id),
        func.sum(func.cast(VerdurasProduct.is_active == True, db.Integer)),  # noqa: E712
    ).filter(VerdurasProduct.business_id == business_id).first()
    n_products = int(_num(catalog[0]))
    n_active = int(_num(catalog[1]))

    context = {
        'vertical': 'verduras',
        'unit_note': 'Cantidades en kg/lb/unidad (fracciones con decimales = gramos).',
        'period_days': days,
        'period_start': str(start),
        'period_end': str(today),
        'currency': 'COP',
        'overall': overall,
        'active_days': len(daily),
        'daily_series': daily,
        'top_products_by_revenue': top_rev,
        'top_products_by_quantity': top_qty,
        'sales_by_weekday': weekday,
        'catalog': {'total': n_products, 'active': n_active},
    }
    # ── FASE 1: inventario, merma y márgenes (escala tendero: barato) ──
    inv = stock_status(business_id)
    inv_items = inv['items']
    context['inventory'] = {
        'items': inv_items,
        'total_value': sum(i['stock_value'] or 0 for i in inv_items),
        'low': [i['name'] for i in inv_items if i['status'] == 'bajo'],
        'out': [i['name'] for i in inv_items if i['status'] == 'agotado'],
        'no_purchases': [i['name'] for i in inv_items
                         if i['status'] == 'sin_compras'],
    }
    month_merma = merma_month(business_id)
    context['merma'] = {
        'month_loss': month_merma['total_loss'],
        'items': month_merma['items'][:5],
    }
    marg = margins(business_id, days)
    context['margins'] = {
        'totals': marg['totals'],
        'items': [{k: it[k] for k in ('name', 'unit', 'qty', 'revenue',
                                      'avg_unit_cost', 'cost', 'margin',
                                      'margin_pct')} for it in marg['items'][:8]],
        'without_cost': marg['without_cost'],
    }
    context['quiet_products'] = [q['name'] for q in quiet_products(business_id)]
    if catalog_details:
        context['catalog_items'] = catalog_details
    return context


# ── Serie/estados compatibles con el handler ─────────────────────────────────

def is_empty_quick_result(res):
    if not res:
        return False
    if 'summary' in res:
        return res['summary'].get('orders', 0) == 0
    if 'items' in res:
        return not res['items']
    return False


def window_label_from_days(days):
    return {
        1: 'Hoy',
        2: 'Ayer',
        7: 'esta semana',
        30: 'este mes',
        60: 'los últimos 60 días',
    }.get(days, f'los últimos {days} días')


def get_data_stage(business_id):
    """Madurez de datos del negocio (Nivel 0-3, mismos umbrales que restaurante)."""
    products = db.session.query(func.count(VerdurasProduct.id)).filter(
        VerdurasProduct.business_id == business_id).scalar() or 0
    sales = _sales_base(business_id).count()
    if products == 0:
        level = 0
    elif sales == 0:
        level = 1
    elif sales < 20:
        level = 2
    else:
        level = 3
    return {'level': level, 'products': products, 'orders': sales}


def has_sales(business_id, days=None):
    q = _sales_base(business_id)
    if days:
        since = _today_utc() - timedelta(days=days)
        q = q.filter(func.date(VerdurasSale.created_at) >= since)
    return q.count() > 0


def projection_uplift(business_id, days=60, adoption=0.25):
    """Proyección con datos reales: 1 de cada 4 ventas suma el producto activo
    más económico (típico: una unidad o porción extra)."""
    today = _today_utc()
    start = today - timedelta(days=days)
    s = _range_summary(business_id, start, today)
    revenue, sales, avg_ticket_v = s['total'], s['orders'], s['avg_ticket']
    cheapest = db.session.query(func.min(VerdurasProduct.current_price)).filter(
        VerdurasProduct.business_id == business_id,
        VerdurasProduct.is_active == True,  # noqa: E712
    ).scalar()
    addon = int(_num(cheapest, default=0)) or 5000
    extra = int(sales * adoption * addon)
    pct = round((extra / revenue) * 100, 1) if revenue else 0
    return {
        'text': (
            f"Analicé tus ventas reales de los últimos {days} días "
            f"({sales} ventas, ticket promedio ${_cop(avg_ticket_v)} COP, "
            f"${_cop(revenue)} COP en total) y proyecté el impacto:\n\n"
            f"Si en 1 de cada 4 ventas (25%) agregas un producto extra "
            f"de ~${_cop(addon)} COP, generarías ${_cop(extra)} COP adicionales "
            f"en este mismo periodo (≈ +{pct}% sobre tus ingresos actuales).\n\n"
            f"Es una proyección con tus datos reales, no un número inventado. "
            f"¿Quieres que afine el cálculo con otro producto o porcentaje?"
        ),
        'revenue': revenue,
        'orders': sales,
        'avg_ticket': avg_ticket_v,
        'addon_price': addon,
        'adoption': adoption,
        'extra_revenue': extra,
        'projected_revenue': revenue + extra,
        'pct': pct,
    }


# ── Estados vacíos y sugerencias (tono verdulería) ───────────────────────────

def _norm(raw):
    out = []
    for s in raw or []:
        if isinstance(s, str):
            out.append({'label': s, 'href': None, 'action': None})
        else:
            out.append({
                'label': s.get('label', ''),
                'href': s.get('href'),
                'action': s.get('action'),
            })
    return out


EMPTY_STATES = {
    'no_catalog': {
        'icon': 'menu_book',
        'text': (
            "👋 ¡Hola! Aún no tienes productos en tu catálogo de la verdulería.\n\n"
            "Para ayudarte a analizar tu negocio, primero carga tus productos "
            "(tomate, papa, cebolla...) con su precio por kg o unidad.\n\n"
            "📦 Créalos en el módulo de Verduras y vuelve aquí."
        ),
        'suggestions': [
            '¿Qué puedes hacer por mí?',
            '¿Cuánto vendí hoy?',
        ],
    },
    'no_sales_yet': {
        'icon': 'celebration',
        'text': (
            "🎉 Veo que ya cargaste tu catálogo. ¡Buenísimo!\n\n"
            "Ahora solo falta registrar tus primeras ventas (por peso o por "
            "unidad). Cuando eso ocurra, podré ayudarte a descubrir:\n\n"
            "• Productos más vendidos por kg\n"
            "• Días fuertes y flojos\n"
            "• Ticket promedio\n"
            "• Tendencias de precio"
        ),
        'suggestions': [
            '¿Qué puedes hacer por mí?',
            '¿Cuál es mi producto más vendido?',
        ],
    },
    'chart_empty': {
        'icon': 'show_chart',
        'text': (
            "📈 Todavía no hay datos para generar esta gráfica.\n\n"
            "Cuando tengas ventas, aquí aparecerán automáticamente."
        ),
        'suggestions': ['¿Qué puedes hacer por mí?'],
    },
}


def build_empty_state(kind, window_label=None):
    if kind == 'no_data_window':
        wl = window_label or 'este periodo'
        return {
            'type': kind,
            'icon': 'bar_chart',
            'text': (
                f"📊 {wl} todavía no hay ventas registradas.\n\n"
                "Cuando empieces a vender, podré analizar tendencias, ticket "
                "promedio, productos más vendidos por kg y mucho más."
            ),
            'suggestions': _norm(['¿Qué puedes hacer por mí?']),
        }
    spec = EMPTY_STATES.get(kind, EMPTY_STATES['chart_empty'])
    return {
        'type': kind,
        'icon': spec['icon'],
        'text': spec['text'],
        'suggestions': _norm(spec['suggestions']),
    }


_LEVEL_0_POOL = [
    {'label': '¿Qué puedes hacer por mí?', 'prompt': '¿Qué puedes hacer por mí?'},
    {'label': '¿Cuánto vendí hoy?', 'prompt': '¿Cuánto vendí hoy?'},
]
_LEVEL_1_POOL = [
    {'label': '¿Cómo empezar a vender más?', 'prompt': '¿Cómo puedo empezar a vender más?'},
    {'label': '¿Qué analiza Copilot?', 'prompt': '¿Qué puedes analizar de mi negocio?'},
]
_LEVEL_2_POOL = [
    {'label': 'Analiza mis ventas', 'prompt': 'Analiza mis ventas del último mes'},
    {'label': 'Producto estrella', 'prompt': '¿Cuál es mi producto más vendido?'},
    {'label': 'Ticket promedio', 'prompt': '¿Cuál es mi ticket promedio?'},
]
_LEVEL_3_POOL = [
    {'label': 'Analiza mis ventas', 'prompt': 'Analiza mis ventas'},
    {'label': 'Producto estrella', 'prompt': '¿Cuál es mi producto más vendido?'},
    {'label': 'Comparar meses', 'prompt': 'Compara mis ventas de este mes con el anterior'},
    {'label': 'Ticket promedio', 'prompt': '¿Cuál es mi ticket promedio?'},
    {'label': 'Ventas por día', 'prompt': '¿Cómo se comportan mis ventas por día de la semana?'},
    {'label': '¿A cómo está el tomate?', 'prompt': '¿A cómo está el tomate hoy?'},
]


def welcome_suggestions(business_id, stage):
    level = stage['level']
    pool = {0: _LEVEL_0_POOL, 1: _LEVEL_1_POOL, 2: _LEVEL_2_POOL}.get(level, _LEVEL_3_POOL)
    return random.sample(pool, min(4, len(pool)))


_FOLLOWUP_POOLS = {
    'sales_today': ['Ticket promedio', 'Producto más vendido', 'Ventas de la semana'],
    'sales_yesterday': ['Ticket promedio', 'Producto más vendido', 'Ventas de la semana'],
    'week_sales': ['Desglose por día', 'Producto estrella', 'Comparar con mes anterior'],
    'month_sales': ['Producto más vendido', 'vs mes anterior', 'Ticket promedio'],
    'top_product': ['Ventas de la semana', 'Ticket promedio', 'Comparar meses'],
    'avg_ticket': ['Ventas semanales', 'Comparar meses', 'Producto estrella'],
    'compare_months': ['Tendencia general', 'Ticket promedio', 'Producto estrella'],
    'new_customers': ['Ventas totales', 'Producto más vendido', 'Ticket promedio'],
    'sales_analysis': ['Producto estrella', 'Comparar meses', 'Ticket promedio'],
    'stock_status': ['¿Qué debo reponer?', 'Merma del mes', 'Analiza mis ventas'],
    'merma_month': ['¿Qué producto pierde más?', 'Rentabilidad del mes', '¿Qué debo reponer?'],
    'restock': ['Merma del mes', 'Rentabilidad del mes', 'Ventas de la semana'],
    'waste_analysis': ['¿Qué debo reponer?', 'Rentabilidad del mes', 'Producto estrella'],
    'profitability_analysis': ['¿Qué debo reponer?', 'Merma del mes', 'Producto estrella'],
    'general_analysis': [
        '¿Cuál es mi producto más vendido?',
        'Compara mis ventas por día',
        '¿Cuál es mi ticket promedio?',
    ],
}


def followup_suggestions(cls=None, last_intent=None, business_id=None,
                         stage=None, seen_intents=None):
    """Chips post-respuesta para verdulería (sin enriquecimiento con datos: FASE 0)."""
    intent = last_intent or (cls.get('intent') if cls else None)
    level = stage['level'] if stage else 3
    if level < 2:
        pool = ['Analiza mis ventas', '¿Cuál es mi producto más vendido?']
    else:
        pool = _FOLLOWUP_POOLS.get(intent, _FOLLOWUP_POOLS['general_analysis'])
    return [
        {'label': s, 'prompt': s, 'icon': 'chat'} for s in pool[:3]
    ]


def weekly_sales_by_day(business_id, days=7):
    """Ventas por día de semana (0=lun..6=dom), calculado en Python (portable)."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (today - timedelta(days=days - 1)).date()
    series = daily_series_since(business_id, start)
    labels = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    money = {i: 0 for i in range(7)}
    for d, t in series:
        if d is not None:
            money[d.weekday()] += t
    return {'labels': labels, 'money': [money[i] for i in range(7)]}


def business_display_name(business_id):
    """Nombre del negocio para el prompt (sin acoplar a context.py del módulo)."""
    biz = db.session.get(Business, business_id)
    return biz.name if biz else None


# ── FASE 1: inventario, merma, rentabilidad y reposición ─────────────────────
# Lee MODELOS (contrato estable), no el service del módulo. Fórmulas idénticas
# a verduras/services/inventory.py. Todo en Decimal; el texto sale en COP.

_CENTS = Decimal('0.01')


def _dec(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def _qty_str(value, unit):
    return f"{float(_dec(value)):g} {unit}"


def _product_sales(business_id, product_id, since):
    """(qty Decimal, revenue int) del producto desde `since` (no canceladas)."""
    row = db.session.query(
        func.coalesce(func.sum(VerdurasSaleItem.quantity), 0),
        func.coalesce(func.sum(VerdurasSaleItem.line_total), 0),
    ).join(VerdurasSale, VerdurasSale.id == VerdurasSaleItem.sale_id).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSaleItem.product_id == product_id,
        VerdurasSale.status != 'cancelled',
        func.date(VerdurasSale.created_at) >= since,
    ).first()
    return _dec(row[0]), int(_dec(row[1]))


def _avg_daily_sales(business_id, product_id, days=14):
    qty, _ = _product_sales(business_id, product_id, _today_utc() - timedelta(days=days))
    return qty / days if days else Decimal(0)


def _weighted_avg_cost(business_id, product_id):
    """Costo unitario ponderado por cantidad (== inventory.average_unit_cost)."""
    row = db.session.query(
        func.sum(VerdurasLot.quantity),
        func.sum(VerdurasLot.total_cost),
    ).filter(
        VerdurasLot.business_id == business_id,
        VerdurasLot.product_id == product_id,
    ).first()
    qty, cost = _dec(row[0]), _dec(row[1])
    if qty <= 0:
        return None
    return (cost / qty).quantize(_CENTS)


def _last_sale_date(business_id, product_id):
    row = db.session.query(func.max(func.date(VerdurasSale.created_at))).join(
        VerdurasSaleItem, VerdurasSaleItem.sale_id == VerdurasSale.id,
    ).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSaleItem.product_id == product_id,
        VerdurasSale.status != 'cancelled',
    ).first()
    return _as_date(row[0]) if row and row[0] is not None else None


def _stock_of(business_id, product):
    """Stock derivado (compras − ventas − merma) + costo ponderado."""
    bought = _dec(db.session.query(func.sum(VerdurasLot.quantity)).filter(
        VerdurasLot.business_id == business_id,
        VerdurasLot.product_id == product.id).scalar())
    sold, _ = _product_sales(business_id, product.id, _date(2000, 1, 1))
    lost = _dec(db.session.query(func.sum(VerdurasMerma.quantity)).filter(
        VerdurasMerma.business_id == business_id,
        VerdurasMerma.product_id == product.id).scalar())
    stock = bought - sold - lost
    avg_cost = _weighted_avg_cost(business_id, product.id)
    value = (stock * avg_cost).quantize(_CENTS) if avg_cost is not None and stock > 0 else None
    return {
        'product_id': product.id, 'name': product.name, 'unit': product.unit,
        'purchased': bought, 'sold': sold, 'merma_qty': lost,
        'stock': stock, 'avg_unit_cost': avg_cost, 'stock_value': value,
    }


def _active_products(business_id):
    return (VerdurasProduct.query.filter_by(
        business_id=business_id, is_active=True)
        .order_by(VerdurasProduct.name).all())


def stock_status(business_id, cover_days=3, history_days=14):
    """Estado de inventario con cobertura en días y alertas (Nivel 1).

    status: 'ok' | 'bajo' (cobertura < cover_days) | 'agotado' (stock <= 0)
    | 'sin_compras' (sin lotes: no hay de dónde calcular).
    """
    items = []
    for p in _active_products(business_id):
        s = _stock_of(business_id, p)
        avg = _avg_daily_sales(business_id, p.id, history_days)
        coverage = (s['stock'] / avg) if avg > 0 else None
        if s['purchased'] <= 0:
            status = 'sin_compras'
        elif s['stock'] <= 0:
            status = 'agotado'
        elif coverage is not None and coverage < cover_days:
            status = 'bajo'
        else:
            status = 'ok'
        items.append({
            'name': p.name, 'unit': p.unit,
            'stock': float(s['stock']),
            'coverage_days': round(float(coverage), 1) if coverage is not None else None,
            'stock_value': int(s['stock_value']) if s['stock_value'] is not None else None,
            'status': status,
        })
    rank = {'agotado': 0, 'bajo': 1, 'sin_compras': 2, 'ok': 3}
    items.sort(key=lambda i: (rank[i['status']],
                              i['coverage_days'] if i['coverage_days'] is not None else 1e9))
    if not items:
        return {'text': 'No tienes productos activos en el catálogo.', 'items': []}
    marks = {'agotado': '🔴 AGOTADO', 'bajo': '🟡 BAJO', 'sin_compras': '⚪ SIN COMPRAS', 'ok': '🟢'}
    lines = []
    for it in items:
        cov = f"cobertura ~{it['coverage_days']} días" if it['coverage_days'] is not None else 'sin historial de venta'
        val = f" — valor ${_cop(it['stock_value'])}" if it['stock_value'] is not None else ''
        lines.append(f"• {it['name']}: {_qty_str(it['stock'], it['unit'])} "
                     f"({cov}){val} {marks[it['status']]}")
    return {'text': '📦 Estado de inventario:\n' + '\n'.join(lines), 'items': items}


def quiet_products(business_id, days=14):
    """Productos activos sin ventas en los últimos `days` días."""
    since = _today_utc() - timedelta(days=days)
    out = []
    for p in _active_products(business_id):
        qty, _ = _product_sales(business_id, p.id, since)
        if qty > 0:
            continue
        last = _last_sale_date(business_id, p.id)
        out.append({
            'name': p.name, 'unit': p.unit,
            'days_since_last_sale': ( _today_utc() - last).days if last else None,
        })
    return out


def merma_month(business_id, ref_date=None):
    """Merma del mes calendario (Nivel 1): pérdida congelada en COP."""
    ref = ref_date or _today_utc()
    start, end = ref.replace(day=1), ref
    rows = db.session.query(
        VerdurasMerma.product_id,
        VerdurasProduct.name,
        VerdurasProduct.unit,
        func.sum(VerdurasMerma.quantity).label('qty'),
        func.sum(VerdurasMerma.cost_loss).label('loss'),
    ).join(VerdurasProduct, VerdurasProduct.id == VerdurasMerma.product_id).filter(
        VerdurasMerma.business_id == business_id,
        func.date(VerdurasMerma.registered_at) >= start,
        func.date(VerdurasMerma.registered_at) <= end,
    ).group_by(VerdurasMerma.product_id, VerdurasProduct.name,
               VerdurasProduct.unit).order_by(
        func.sum(VerdurasMerma.cost_loss).desc()).all()
    total_loss = int(sum((_dec(r.loss) for r in rows), Decimal(0)))
    items = [{'name': r.name, 'unit': r.unit,
              'qty': float(_dec(r.qty)), 'loss': int(_dec(r.loss))} for r in rows]
    if not items:
        return {'text': '🎉 Este mes no registraste merma. ¡Bien!',
                'total_loss': 0, 'items': []}
    purch = _dec(db.session.query(func.sum(VerdurasLot.total_cost)).filter(
        VerdurasLot.business_id == business_id,
        func.date(VerdurasLot.purchased_at) >= start,
        func.date(VerdurasLot.purchased_at) <= end).scalar())
    pct_txt = f" ({round(total_loss / float(purch) * 100, 1)}% de tus compras)" if purch > 0 else ''
    top = items[0]
    share = round(top['loss'] / total_loss * 100, 1) if total_loss else 0
    return {
        'text': (
            f"🗑️ Merma de este mes: ${_cop(total_loss)} COP{pct_txt}.\n"
            f"La que más pierde: {top['name']} con ${_cop(top['loss'])} "
            f"({share}% de la merma)."
        ),
        'total_loss': total_loss, 'items': items,
    }


def margins(business_id, days=30):
    """Rentabilidad por producto: ingreso − costo ponderado (Nivel 2).

    Sin lotes del producto no hay costo: va a without_cost, jamás se inventa.
    """
    since = _today_utc() - timedelta(days=days)
    items, without_cost = [], []
    for p in _active_products(business_id):
        qty, revenue = _product_sales(business_id, p.id, since)
        if qty <= 0:
            continue
        avg_cost = _weighted_avg_cost(business_id, p.id)
        if avg_cost is None:
            without_cost.append(p.name)
            continue
        cost = (qty * avg_cost).quantize(_CENTS)
        margin = Decimal(revenue) - cost
        items.append({
            'name': p.name, 'unit': p.unit,
            'qty': float(qty), 'revenue': revenue,
            'avg_unit_cost': float(avg_cost), 'cost': int(cost),
            'margin': int(margin),
            'margin_pct': round(float(margin) / revenue * 100, 1) if revenue else 0,
        })
    items.sort(key=lambda i: i['margin'], reverse=True)
    totals = {
        'revenue': sum(i['revenue'] for i in items),
        'cost': sum(i['cost'] for i in items),
        'margin': sum(i['margin'] for i in items),
    }
    totals['margin_pct'] = (
        round(totals['margin'] / totals['revenue'] * 100, 1) if totals['revenue'] else 0)
    if not items:
        suffix = (f" Sin costo registrado en: {', '.join(without_cost)}." if without_cost else '')
        return {'text': 'Aún no hay ventas con costo registrado en este período.' + suffix,
                'items': [], 'totals': totals, 'without_cost': without_cost}
    lines = [f"{i + 1}. {it['name']}: ganó ${_cop(it['margin'])} "
             f"({it['margin_pct']}%)" for i, it in enumerate(items[:5])]
    suffix = (f"\n⚪ Sin costo (registra sus compras): {', '.join(without_cost)}."
              if without_cost else '')
    return {
        'text': (f"💰 Rentabilidad últimos {days} días: ganaste "
                 f"${_cop(totals['margin'])} COP ({totals['margin_pct']}% "
                 f"sobre ${_cop(totals['revenue'])} vendidos).\n" + '\n'.join(lines) + suffix),
        'items': items, 'totals': totals, 'without_cost': without_cost,
    }


def restock_suggestions(business_id, cover_days=7, history_days=14):
    """Reposición calculada (Nivel 2): venta diaria × días a cubrir − stock.

    Cantidades derivadas de datos reales, con la fórmula a la vista para que
    el LLM la cite en vez de inventar puntos de reorden.
    """
    items = []
    for p in _active_products(business_id):
        s = _stock_of(business_id, p)
        avg = _avg_daily_sales(business_id, p.id, history_days)
        if avg <= 0:
            continue
        coverage = s['stock'] / avg
        suggested = max(Decimal(0), avg * cover_days - s['stock'])
        est_cost = (suggested * s['avg_unit_cost']).quantize(_CENTS) \
            if s['avg_unit_cost'] is not None else None
        items.append({
            'name': p.name, 'unit': p.unit,
            'stock': float(s['stock']),
            'avg_daily': float(avg.quantize(Decimal('0.001'))),
            'coverage_days': round(float(coverage), 1),
            'suggested': float(suggested.quantize(Decimal('0.001'))),
            'est_cost': int(est_cost) if est_cost is not None else None,
            'cover_days': cover_days, 'history_days': history_days,
        })
    items.sort(key=lambda i: i['coverage_days'])
    buy = [i for i in items if i['suggested'] > 0]
    if not buy:
        return {'text': f'✅ Con el ritmo actual cubres más de {cover_days} días en todo.',
                'items': items}
    lines = []
    for it in buy[:7]:
        cost = f" (~${_cop(it['est_cost'])})" if it['est_cost'] is not None else ''
        lines.append(f"• {it['name']}: compra {_qty_str(it['suggested'], it['unit'])}{cost} "
                     f"(te quedan {_qty_str(it['stock'], it['unit'])}, "
                     f"cobertura {it['coverage_days']} días)")
    return {'text': f'🛒 Para cubrir {cover_days} días al ritmo de los últimos '
                    f'{history_days} días:\n' + '\n'.join(lines),
            'items': items}

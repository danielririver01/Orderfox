"""
data_service.py — Capa de datos de Copilot VZ.

PostgreSQL calcula, Flask organiza. Aquí NO hay lógica de IA: solo
consultas SQL agregadas que devuelven datos procesados (nunca filas
crudas) para que Flask los envíe como contexto al LLM o los responda
directo en las consultas rápidas (Nivel 1).
"""

import random
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, extract

from app import db
from app.models import Order, OrderItem, Product, Category


def _today_utc():
    return datetime.now(timezone.utc).date()


def _range_summary(restaurant_id, start, end):
    """Suma total, nº pedidos y ticket promedio en [start, end] (UTC)."""
    rows = db.session.query(
        func.coalesce(func.sum(Order.total), 0),
        func.count(Order.id),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start,
        func.date(Order.created_at) <= end,
    ).first()
    total = int(rows[0] or 0)
    orders = int(rows[1] or 0)
    avg = round(total / orders) if orders else 0
    return {'total': total, 'orders': orders, 'avg_ticket': avg}


def sales_for_date(restaurant_id, days_ago=0):
    base = _today_utc() - timedelta(days=days_ago)
    s = _range_summary(restaurant_id, base, base)
    label = 'hoy' if days_ago == 0 else ('ayer' if days_ago == 1 else f'hace {days_ago} días')
    avg_txt = f". Ticket promedio: ${'{:,}'.format(s['avg_ticket']).replace(',', '.')}" if s['orders'] else ''
    return {
        'text': (
            f"{'Hoy' if days_ago == 0 else 'Ayer'} vendiste "
            f"${'{:,}'.format(s['total']).replace(',', '.')} COP en {s['orders']} pedidos{avg_txt}."
        ),
        'summary': s,
        'label': label,
    }


def top_products(restaurant_id, days=30, limit=5):
    since = _today_utc() - timedelta(days=days)
    rows = db.session.query(
        OrderItem.product_name,
        func.sum(OrderItem.quantity).label('qty'),
        func.sum(OrderItem.subtotal).label('rev'),
    ).join(Order, Order.id == OrderItem.order_id).filter(
        OrderItem.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= since,
    ).group_by(OrderItem.product_name).order_by(func.sum(OrderItem.subtotal).desc()).limit(limit).all()
    items = [{'name': r.product_name, 'qty': int(r.qty), 'revenue': int(r.rev)} for r in rows]
    if not items:
        return {'text': 'Aún no tienes ventas registradas en este período.', 'items': []}
    top = items[0]
    text = 'Productos más vendidos (por ingresos):\n' + '\n'.join(
        f"{i+1}. {it['name']} — ${it['revenue']:,} COP ({it['qty']} ud.)" for i, it in enumerate(items)
    )
    return {'text': text, 'items': items}


def avg_ticket(restaurant_id, days=30):
    s = _range_summary(restaurant_id, _today_utc() - timedelta(days=days), _today_utc())
    return {
        'text': (
            f"Tu ticket promedio es ${s['avg_ticket']:,} COP "
            f"({s['orders']} pedidos en los últimos {days} días)."
        ),
        'summary': s,
    }


def new_customers(restaurant_id, days_ago=0):
    base = _today_utc() - timedelta(days=days_ago)
    count = db.session.query(func.count(func.distinct(Order.customer_phone))).filter(
        Order.restaurant_id == restaurant_id,
        func.date(Order.created_at) == base,
        Order.customer_phone.isnot(None),
    ).scalar() or 0
    label = 'hoy' if days_ago == 0 else ('ayer' if days_ago == 1 else f'hace {days_ago} días')
    return {'text': f"Tuviste {count} cliente(s) nuevo(s) {label}.", 'count': count}


def compare_months(restaurant_id):
    today = _today_utc()
    # Mes actual (desde el día 1) vs mes anterior completo.
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    cur = _range_summary(restaurant_id, first_this, today)
    prev = _range_summary(restaurant_id, first_prev, last_prev)
    if prev['total'] > 0:
        pct = round(((cur['total'] - prev['total']) / prev['total']) * 100, 1)
        trend = f"{pct:+}%" 
        trend_txt = f" ({trend} vs mes anterior)"
    else:
        trend_txt = ' (mes anterior sin ventas)'
    text = (
        f"Este mes llevas ${cur['total']:,} COP en {cur['orders']} pedidos.\n"
        f"Mes anterior: ${prev['total']:,} COP en {prev['orders']} pedidos{trend_txt}."
    )
    return {'text': text, 'current': cur, 'previous': prev}


def sales_window(restaurant_id, days=7):
    s = _range_summary(restaurant_id, _today_utc() - timedelta(days=days), _today_utc())
    label = 'esta semana' if days <= 7 else f'los últimos {days} días'
    return {
        'text': f"Ventas de {label}: ${s['total']:,} COP en {s['orders']} pedidos.",
        'summary': s,
    }


# ── Despacho de consultas rápidas (Nivel 1) ──────────────────────────────────

def handle_quick(restaurant_id, intent):
    if intent == 'sales_today':
        return sales_for_date(restaurant_id, 0)
    if intent == 'sales_yesterday':
        return sales_for_date(restaurant_id, 1)
    if intent == 'orders_today':
        s = _range_summary(restaurant_id, _today_utc(), _today_utc())
        return {'text': f"Tuviste {s['orders']} pedidos hoy.", 'summary': s}
    if intent == 'top_product':
        return top_products(restaurant_id, 30, 5)
    if intent == 'avg_ticket':
        return avg_ticket(restaurant_id, 30)
    if intent == 'new_customers':
        return new_customers(restaurant_id, 0)
    if intent == 'compare_months':
        return compare_months(restaurant_id)
    if intent == 'week_sales':
        return sales_window(restaurant_id, 7)
    if intent == 'month_sales':
        return sales_window(restaurant_id, 30)
    # Fallback: resumen de hoy.
    return sales_for_date(restaurant_id, 0)


# ── Contexto enriquecido para el LLM (Nivel 2) ──────────────────────────────

def build_context(restaurant_id, days=90):
    """
    Devuelve un dict de datos YA procesados para enviar como contexto al LLM.
    Nunca enviamos filas crudas: PostgreSQL agrega, Flask organiza.
    """
    today = _today_utc()
    start = today - timedelta(days=days)

    # Serie diaria agregada (máx ~90 registros → pocos tokens).
    series = db.session.query(
        func.date(Order.created_at).label('d'),
        func.coalesce(func.sum(Order.total), 0).label('total'),
        func.count(Order.id).label('orders'),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start,
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()

    daily = [{'date': str(r.d), 'total': int(r.total), 'orders': int(r.orders)} for r in series]

    overall = _range_summary(restaurant_id, start, today)

    # Productos top por ingresos y por cantidad.
    top_rev = top_products(restaurant_id, days, 8)['items']
    top_qty_rows = db.session.query(
        OrderItem.product_name,
        func.sum(OrderItem.quantity).label('qty'),
    ).join(Order, Order.id == OrderItem.order_id).filter(
        OrderItem.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start,
    ).group_by(OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(8).all()
    top_qty = [{'name': r.product_name, 'qty': int(r.qty)} for r in top_qty_rows]

    # Ventas por día de la semana (0=lunes..6=domingo).
    # DAYOFWEEK(): 1=domingo..7=sábado (MySQL y MariaDB compatibles).
    wk = db.session.query(
        func.dayofweek(Order.created_at).label('dow'),
        func.coalesce(func.sum(Order.total), 0).label('total'),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start,
    ).group_by(func.dayofweek(Order.created_at)).all()
    # Mapear 1=dom..7=sab → 0=lun..6=dom
    weekday = {i: 0 for i in range(7)}
    for r in wk:
        idx = (int(r.dow) - 2) % 7
        weekday[idx] += int(r.total)

    catalog = db.session.query(
        func.count(Product.id),
        func.sum(func.cast(Product.is_active == True, db.Integer)),
    ).filter(Product.restaurant_id == restaurant_id).first()
    n_products = int(catalog[0] or 0)
    n_active = int(catalog[1] or 0)

    return {
        'period_days': days,
        'currency': 'COP',
        'overall': overall,
        'active_days': len(daily),
        'daily_series': daily,
        'top_products_by_revenue': top_rev,
        'top_products_by_quantity': top_qty,
        'sales_by_weekday': weekday,  # 0=lunes..6=domingo
        'catalog': {'total': n_products, 'active': n_active},
    }


# ── Serie diaria para gráficas ───────────────────────────────────────────────

def daily_series_since(restaurant_id, start):
    """Retorna [(date, total), ...] para cada día desde start hasta hoy."""
    rows = db.session.query(
        func.date(Order.created_at).label('d'),
        func.coalesce(func.sum(Order.total), 0).label('total'),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        func.date(Order.created_at) >= start,
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
    return [(r.d, int(r.total)) for r in rows]


# ── Estados vacíos inteligentes (sin LLM, sin crédito) ───────────────────────
# Nunca respondemos "No hay datos.": el backend sabe si hay información y
# devuelve un estado vacío útil y motivador. Esto ahorra llamadas al modelo
# y créditos innecesarios.

EMPTY_STATES = {
    # Nivel 0: sin catálogo.
    'no_catalog': {
        'icon': 'menu_book',
        'text': (
            "👋 ¡Hola! Aún no tienes productos en tu catálogo.\n\n"
            "Para que pueda ayudarte a analizar tu negocio, primero crea tu catálogo.\n\n"
            "📦 Puedes crear tus productos manualmente en el dashboard."
        ),
        # Sugerencias como acciones reales dentro del chat (onboarding).
        'suggestions': [
            {'label': 'Crear mi primera categoría', 'action': 'category'},
            {'label': 'Crear mi primer producto', 'action': 'product'},
        ],
    },
    # Nivel 1: hay catálogo, pero cero ventas (proactivo y motivador).
    'no_sales_yet': {
        'icon': 'celebration',
        'text': (
            "🎉 Veo que ya cargaste tu menú. ¡Buenísimo!\n\n"
            "Ahora solo falta registrar tus primeras ventas. Cuando eso ocurra, podré "
            "ayudarte a descubrir:\n\n"
            "• Productos más vendidos\n"
            "• Horas pico\n"
            "• Ticket promedio\n"
            "• Tendencias"
        ),
        'suggestions': [
            {'label': 'Registrar mis primeros pedidos', 'action': 'order'},
            '¿Qué puedes hacer por mí?',
        ],
    },
    # Caso 3: pidió una gráfica pero no hay datos.
    'chart_empty': {
        'icon': 'show_chart',
        'text': (
            "📈 Todavía no hay datos para generar esta gráfica.\n\n"
            "Cuando tengas ventas, aquí aparecerán automáticamente."
        ),
        'suggestions': ['¿Qué puedes hacer por mí?'],
    },
}


def _normalize_suggestions(raw):
    """Acepta strings (mensaje de chat), dicts {'label','href'} (link real)
    o dicts {'label','action'} (acción de onboarding dentro del chat)."""
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


def window_label_from_days(days):
    return {
        1: 'Hoy',
        2: 'Ayer',
        7: 'esta semana',
        30: 'este mes',
        60: 'los últimos 2 meses',
        90: 'los últimos 90 días',
    }.get(days, f'los últimos {days} días')


def build_empty_state(kind, window_label=None):
    if kind == 'no_data_window':
        wl = window_label or 'este periodo'
        return {
            'type': kind,
            'icon': 'bar_chart',
            'text': (
                f"📊 {wl} todavía no hay ventas registradas.\n\n"
                "Cuando empieces a vender, podré analizar tendencias, ticket promedio, "
                "productos más vendidos y mucho más."
            ),
            'suggestions': _normalize_suggestions([
                '¿Qué puedes hacer por mí?',
                {'label': 'Ver mis productos', 'href': '/dashboard/products'},
            ]),
        }
    spec = EMPTY_STATES.get(kind, EMPTY_STATES['chart_empty'])
    return {
        'type': kind,
        'icon': spec['icon'],
        'text': spec['text'],
        'suggestions': _normalize_suggestions(spec['suggestions']),
    }


def get_data_stage(restaurant_id):
    """Etapa de madurez de datos del restaurante (Nivel 0-3)."""
    products = db.session.query(func.count(Product.id)).filter(
        Product.restaurant_id == restaurant_id).scalar() or 0
    orders = db.session.query(func.count(Order.id)).filter(
        Order.restaurant_id == restaurant_id).scalar() or 0
    if products == 0:
        level = 0
    elif orders == 0:
        level = 1
    elif orders < 20:
        level = 2
    else:
        level = 3
    return {'level': level, 'products': products, 'orders': orders}


def has_sales(restaurant_id, days=None):
    q = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
    )
    if days:
        since = _today_utc() - timedelta(days=days)
        q = q.filter(func.date(Order.created_at) >= since)
    return q.count() > 0


def projection_uplift(restaurant_id, days=90, adoption=0.25):
    """Proyección transparente del impacto de mejorar el ticket promedio.

    Estima el ingreso adicional si una fracción (`adoption`) de los pedidos
    suma un item adicional cuyo precio es el producto más económico activo
    del catálogo (típico: una bebida o acompañamiento). Todos los números
    vienen de datos reales del restaurante, no son inventados.
    """
    today = _today_utc()
    start = today - timedelta(days=days)
    s = _range_summary(restaurant_id, start, today)
    revenue = s['total']
    orders = s['orders']
    avg_ticket = s['avg_ticket']

    # Precio de un item adicional típico = producto activo más económico.
    cheapest = db.session.query(func.min(Product.price)).filter(
        Product.restaurant_id == restaurant_id,
        Product.is_active == True,
    ).scalar()
    addon = int(cheapest) if cheapest else 6000

    extra_revenue = int(orders * adoption * addon)
    projected = revenue + extra_revenue
    pct = round((extra_revenue / revenue) * 100, 1) if revenue else 0
    return {
        'text': (
            f"Analicé tus ventas reales de los últimos {days} días "
            f"({orders} pedidos, ticket promedio ${'{:,}'.format(avg_ticket).replace(',', '.')} COP, "
            f"${'{:,}'.format(revenue).replace(',', '.')} COP en total) y proyecté el impacto:\n\n"
            f"Si en 1 de cada 4 pedidos (25%) agregas una bebida o acompañamiento "
            f"de ~${'{:,}'.format(addon).replace(',', '.')} COP, generarías ${'{:,}'.format(extra_revenue).replace(',', '.')} COP adicionales "
            f"en este mismo periodo (≈ +{pct}% sobre tus ingresos actuales).\n\n"
            f"Es una proyección con tus datos reales, no un número inventado. "
            f"¿Quieres que afine el cálculo con otro tipo de producto o porcentaje?"
        ),
        'revenue': revenue,
        'orders': orders,
        'avg_ticket': avg_ticket,
        'addon_price': addon,
        'adoption': adoption,
        'extra_revenue': extra_revenue,
        'projected_revenue': projected,
        'pct': pct,
    }


def is_empty_quick_result(res):
    """Detecta si el resultado de una consulta rápida no tiene datos reales."""
    if not res:
        return False
    if 'summary' in res:
        return res['summary'].get('orders', 0) == 0
    if 'items' in res:  # top_products
        return not res['items']
    return False


# ── Welcome screen suggestion pools ──

_LEVEL_0_POOL = [
    {'label': 'Crear mi primer producto', 'prompt': 'Quiero crear mi primer producto'},
    {'label': '¿Qué puede hacer Copilot?', 'prompt': '¿Qué puedes hacer por mí?'},
    {'label': 'Configurar mi restaurante', 'prompt': 'Ayúdame a configurar mi restaurante'},
    {'label': 'Organizar mi menú', 'prompt': 'Ayúdame a organizar mi menú'},
]
_LEVEL_1_POOL = [
    {'label': 'Registrar una venta', 'prompt': 'Quiero registrar una venta de prueba'},
    {'label': '¿Cómo empezar a vender?', 'prompt': '¿Cómo puedo empezar a vender más?'},
    {'label': '¿Qué analiza Copilot?', 'prompt': '¿Qué puedes analizar de mi negocio?'},
    {'label': 'Tips para empezar', 'prompt': 'Dame consejos para empezar a vender'},
]
_LEVEL_2_POOL = [
    {'label': 'Analiza mis ventas', 'prompt': 'Analiza mis ventas del último mes'},
    {'label': 'Producto estrella', 'prompt': '¿Cuál es mi producto más vendido?'},
    {'label': 'Ticket promedio', 'prompt': '¿Cuál es mi ticket promedio?'},
    {'label': '¿Qué puedo mejorar?', 'prompt': '¿Qué puedo mejorar en mi negocio?'},
]
_LEVEL_3_POOL = [
    {'label': 'Analiza mis ventas', 'prompt': 'Analiza mis ventas'},
    {'label': 'Producto estrella', 'prompt': '¿Cuál es mi producto más vendido?'},
    {'label': '¿Qué puedo mejorar?', 'prompt': '¿Qué puedo mejorar esta semana?'},
    {'label': 'Comparar meses', 'prompt': 'Compara mis ventas de este mes con el anterior'},
    {'label': 'Proyectar ventas', 'prompt': 'Proyecta mis ventas para el próximo mes'},
    {'label': 'Ticket promedio', 'prompt': '¿Cuál es mi ticket promedio?'},
    {'label': 'Ventas por día', 'prompt': '¿Cómo se comportan mis ventas por día de la semana?'},
    {'label': 'Ideas de promoción', 'prompt': 'Recomiéndame promociones para aumentar ventas'},
]


def welcome_suggestions(restaurant_id, stage):
    """Sugerencias para la pantalla de bienvenida según madurez de datos."""
    level = stage['level']
    if level == 0:
        pool = _LEVEL_0_POOL
    elif level == 1:
        pool = _LEVEL_1_POOL
    elif level == 2:
        pool = _LEVEL_2_POOL
    else:
        pool = _LEVEL_3_POOL
    n = min(4, len(pool))
    return random.sample(pool, n)


# ── Helpers para datos reales (reutilizados por welcome y follow-up) ──


def _top_product(restaurant_id):
    """Producto más vendido por cantidad."""
    return (
        db.session.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label('qty'),
            func.sum(OrderItem.subtotal).label('revenue'),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != 'cancelled',
        )
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .first()
    )


def _month_sales(restaurant_id):
    """Ventas agregadas del mes actual y anterior."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    next_month_start = (prev_month_start + timedelta(days=32)).replace(day=1)

    this = (
        db.session.query(
            func.count(Order.id).label('orders'),
            func.sum(Order.total).label('revenue'),
            func.avg(Order.total).label('avg_ticket'),
        )
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != 'cancelled',
            Order.created_at >= month_start,
            Order.created_at < next_month_start,
        )
        .first()
    )
    prev = (
        db.session.query(
            func.count(Order.id).label('orders'),
            func.sum(Order.total).label('revenue'),
            func.avg(Order.total).label('avg_ticket'),
        )
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != 'cancelled',
            Order.created_at >= prev_month_start,
            Order.created_at < month_start,
        )
        .first()
    )
    return this, prev


def _total_quantity(restaurant_id):
    """Cantidad total de ítems vendidos (no cancelados)."""
    return (
        db.session.query(func.sum(OrderItem.quantity))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != 'cancelled',
        )
        .scalar() or 1
    )


def _ico(label):
    """Icono Material Symbols para un label de sugerencia."""
    m = {
        'producto': 'star',
        'ticket': 'receipt',
        'tendencia': 'trending_up',
        'recomend': 'tips_and_updates',
        'proyecci': 'trending_up',
        'comparar': 'compare_arrows',
        'impacto': 'pulse',
        'grafic': 'bar_chart',
    }
    lower = label.lower()
    for kw, icon in m.items():
        if kw in lower:
            return icon
    return 'chat'


def _enrich_followup(generic_label, restaurant_id):
    """Convierte un label genérico en un objeto con datos reales del restaurante."""
    lower = generic_label.lower()

    if 'ticket' in lower:
        this, prev = _month_sales(restaurant_id)
        if this and this.avg_ticket and this.orders:
            avg = int(this.avg_ticket)
            avg_fmt = f'${avg:,}'.replace(',', '.')
            trend = ''
            if prev and prev.avg_ticket and prev.orders and prev.avg_ticket > 0:
                diff = round((this.avg_ticket - prev.avg_ticket) / prev.avg_ticket * 100)
                if diff > 0:
                    trend = f' · +{diff}%'
                elif diff < 0:
                    trend = f' · {diff}%'
            return {
                'label': f'Ticket promedio: {avg_fmt} COP{trend}',
                'prompt': '¿Cuál es mi ticket promedio?',
                'icon': 'receipt',
            }
        return {'label': generic_label, 'prompt': generic_label, 'icon': 'receipt'}

    if 'producto' in lower and ('estrella' in lower or 'vendido' in lower):
        top = _top_product(restaurant_id)
        total_qty = _total_quantity(restaurant_id)
        if top and top.qty:
            pct = round(top.qty / total_qty * 100)
            return {
                'label': f'{top.product_name} · {int(top.qty)} vend ({pct}%)',
                'prompt': '¿Cuál es mi producto más vendido?',
                'icon': 'star',
            }
        return {'label': generic_label, 'prompt': generic_label, 'icon': 'star'}

    if 'tendencia' in lower or ('profundizar' in lower and 'tendencia' in lower):
        this, prev = _month_sales(restaurant_id)
        if this and prev and prev.revenue and prev.revenue > 0 and this.revenue:
            diff = round((this.revenue - prev.revenue) / prev.revenue * 100)
            sign = '+' if diff > 0 else ''
            return {
                'label': f'Tendencia: {sign}{diff}% vs mes anterior',
                'prompt': 'Analiza la tendencia de mis ventas',
                'icon': 'trending_up',
            }
        return {'label': generic_label, 'prompt': generic_label, 'icon': 'trending_up'}

    if 'vs ' in lower or ('mes' in lower and 'anterior' in lower):
        this, prev = _month_sales(restaurant_id)
        if this and prev and prev.revenue and prev.revenue > 0 and this.revenue:
            diff_pct = round((this.revenue - prev.revenue) / prev.revenue * 100)
            diff_rev = int(this.revenue - prev.revenue)
            diff_fmt = f'${abs(diff_rev):,}'.replace(',', '.')
            sign = '+' if diff_pct > 0 else ''
            return {
                'label': f'{sign}{diff_pct}% · {diff_fmt} COP',
                'prompt': 'Compara mis ventas de este mes con el anterior',
                'icon': 'compare_arrows',
            }
        return {'label': generic_label, 'prompt': generic_label, 'icon': 'compare_arrows'}

    return {'label': generic_label, 'prompt': generic_label, 'icon': _ico(generic_label)}


# ── Follow-up chip pools (contextuales según intent) ──

_FOLLOWUP_POOLS = {
    'sales_today': [
        'Comparar con la semana pasada',
        'Ticket promedio',
        'Producto más vendido',
        'Tendencia de ventas',
    ],
    'sales_yesterday': [
        'Comparar con la semana pasada',
        'Ticket promedio',
        'Producto más vendido',
        'Tendencia de ventas',
    ],
    'week_sales': [
        'Desglose por día',
        'Producto estrella',
        'Comparar con mes anterior',
        'Ticket promedio',
    ],
    'month_sales': [
        'Comparar por semana',
        'Producto más vendido',
        'vs mes anterior',
        'Proyectar próximo mes',
    ],
    'top_product': [
        'Rentabilidad del producto',
        'Proyectar más ventas',
        'Promoción para este producto',
        'Comparar con otros productos',
    ],
    'avg_ticket': [
        'Impacto de subir el ticket',
        'Ventas semanales',
        'Comparar meses',
        'Producto estrella',
    ],
    'compare_months': [
        'Tendencia general',
        'Recomendaciones',
        'Proyección próximo mes',
        'Ticket promedio',
    ],
    'new_customers': [
        'Ventas totales',
        'Producto más vendido',
        'Ticket promedio',
        'Fidelizar clientes',
    ],
    'sales_analysis': [
        'Profundizar tendencia',
        'Producto estrella',
        'Recomendaciones',
        'Proyección',
    ],
    'profitability_analysis': [
        'Desglose por producto',
        '¿Dónde perder dinero?',
        'Proyección de ganancias',
        'Reducir costos',
    ],
    'recommendations': [
        'Calcular impacto',
        'Producto estrella',
        'Comparar semanas',
        'Ticket promedio',
    ],
    'trend_analysis': [
        'Ver tendencia completa',
        'Predecir próximo mes',
        'Recomendaciones',
        'Impacto de cambios',
    ],
    'executive_report': [
        'Ver gráfica completa',
        'Producto estrella',
        'Ticket promedio',
        'Proyectar',
    ],
    'calc_impact': [
        'Aplicar mejora real',
        'Comparar meses',
        'Producto estrella',
        'Ticket promedio',
    ],
    'general_analysis': [
        'Hazme una gráfica de ventas',
        'Calcula el impacto de mejorar mi ticket promedio',
        '¿Cuál es mi producto más vendido?',
        'Compara mis ventas por día',
    ],
}

_FOLLOWUP_LEVEL_1_2 = [
    'Analiza mis ventas',
    '¿Cuál es mi producto más vendido?',
    '¿Cuál es mi ticket promedio?',
    '¿Qué puedo mejorar?',
]

_INTENT_KEYWORDS = {
    'ventas': ('sales_today', 'sales_yesterday', 'week_sales', 'month_sales'),
    'producto': ('top_product',),
    'ticket': ('avg_ticket',),
    'comparar': ('compare_months',),
    'clientes': ('new_customers',),
    'tendencia': ('trend_analysis', 'sales_analysis'),
    'recomend': ('recommendations',),
    'proyect': ('trend_analysis',),
    'promoci': ('recommendations',),
}


def _label_matches_intents(label, seen_intents):
    """True si la etiqueta de sugerencia ya fue cubierta por algún intent visto."""
    lower = label.lower()
    for keyword, intents in _INTENT_KEYWORDS.items():
        if keyword in lower:
            return any(i in seen_intents for i in intents)
    return False


def followup_suggestions(cls=None, last_intent=None, stage=None, seen_intents=None, restaurant_id=None):
    """Sugerencias contextuales según el último intent y el historial de la conversación.

    Si se proporciona restaurant_id, enriquece los labels genéricos con datos reales
    (ej. 'Producto estrella' → '🍔 Hamburguesa · 45 vend').
    """
    intent = last_intent or (cls.get('intent') if cls else None)
    level = stage['level'] if stage else 3

    if level < 2:
        pool = _FOLLOWUP_LEVEL_1_2
    else:
        pool = _FOLLOWUP_POOLS.get(intent, _FOLLOWUP_POOLS['general_analysis'])

    if seen_intents and pool:
        filtered = [s for s in pool if not _label_matches_intents(s, seen_intents)]
        if filtered:
            pool = filtered

    suggestions = pool[:3]

    if restaurant_id and level >= 2:
        suggestions = [_enrich_followup(s, restaurant_id) for s in suggestions]

    return suggestions


# ── Datos para dashboard weekly stats ────────────────────────────────────────

def weekly_sales_by_day(restaurant_id, days=7):
    """Ventas e pedidos por día de la semana (0=lun..6=dom).

    Devuelve ``{labels: [...], money: [...], orders: [...]}``.
    Ligero — solo dos queries pequeñas, sin build_context completo.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)

    # Dinero por día de semana
    wk_money = db.session.query(
        func.dayofweek(Order.created_at).label('dow'),
        func.coalesce(func.sum(Order.total), 0).label('total'),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        Order.created_at >= start,
    ).group_by(func.dayofweek(Order.created_at)).all()

    # Pedidos por día de semana
    wk_orders = db.session.query(
        func.dayofweek(Order.created_at).label('dow'),
        func.count(Order.id).label('cnt'),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        Order.created_at >= start,
    ).group_by(func.dayofweek(Order.created_at)).all()

    labels = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    money = {i: 0 for i in range(7)}
    orders = {i: 0 for i in range(7)}

    for r in wk_money:
        idx = (int(r.dow) - 2) % 7
        money[idx] = int(r.total)

    for r in wk_orders:
        idx = (int(r.dow) - 2) % 7
        orders[idx] = int(r.cnt)

    return {
        'labels': labels,
        'money': [money[i] for i in range(7)],
        'orders': [orders[i] for i in range(7)],
    }


# ── Tendencia de ingresos 30 días ──────────────────────────────────────────

def revenue_trend_30d(restaurant_id):
    """Ventas diarias de los últimos 30 días agrupadas por día.

    Devuelve ``{labels: [...], values: [...]}``.
    labels formateados como "01 Ene", "02 Ene", etc.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=29)

    rows = db.session.query(
        func.date(Order.created_at).label('d'),
        func.coalesce(func.sum(Order.total), 0).label('total'),
    ).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'cancelled',
        Order.created_at >= start,
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()

    months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
              'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

    data_map = {str(r.d): int(r.total) for r in rows}
    labels = []
    values = []
    for i in range(30):
        day = start + timedelta(days=i)
        day_str = str(day.date())
        labels.append(f'{day.day:02d} {months[day.month - 1]}')
        values.append(data_map.get(day_str, 0))

    return {'labels': labels, 'values': values}

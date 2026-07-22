"""
chart_service.py — Generación y limpieza de gráficas para Copilot VZ.

Genera charts para consultas rápidas (Nivel 1) directamente desde datos
agregados, y limpia/sanea los charts que devuelve el LLM para que Chart.js
no falle al renderizar (valores no numéricos, labels desalineadas, etc.).
"""

from datetime import datetime, timezone, timedelta

from app.services.insights import data_service


VALID_CHART_TYPES = {'line', 'bar', 'doughnut', 'pie'}


def chart_for_intent(restaurant_id, intent, result):
    """Genera chart para consultas rápidas cuando los datos lo ameritan."""
    today = datetime.now(timezone.utc).date()
    days_labels = {0: 'Dom', 1: 'Lun', 2: 'Mar', 3: 'Mié', 4: 'Jue', 5: 'Vie', 6: 'Sáb'}
    def dl(d):
        if d == today: return 'Hoy'
        if d == today - timedelta(days=1): return 'Ayer'
        return days_labels.get(d.weekday(), '')

    if intent in ('sales_today', 'sales_yesterday'):
        start = today - timedelta(days=6)
        series = dict(data_service.daily_series_since(restaurant_id, start))
        labels, data = [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            labels.append(dl(d))
            data.append(series.get(d, 0))
        return {'type': 'bar', 'title': 'Ventas últimos 7 días', 'labels': labels,
                'datasets': [{'label': 'Ventas ($)', 'data': data}]}

    if intent == 'top_product':
        items = (result or {}).get('items', [])
        if not items: return None
        labels = [i['name'][:20] for i in items]
        data = [i['revenue'] for i in items]
        return {'type': 'bar', 'title': 'Top productos por ingresos', 'labels': labels,
                'datasets': [{'label': 'Ingresos ($)', 'data': data}]}

    if intent == 'compare_months':
        cur = (result or {}).get('current', {})
        prev = (result or {}).get('previous', {})
        labels = ['Mes anterior', 'Mes actual']
        data = [prev.get('total', 0), cur.get('total', 0)]
        return {'type': 'bar', 'title': 'Comparación mensual', 'labels': labels,
                'datasets': [{'label': 'Ventas ($)', 'data': data}]}

    if intent == 'week_sales':
        start = today - timedelta(days=6)
        series = dict(data_service.daily_series_since(restaurant_id, start))
        labels, data = [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            labels.append(dl(d))
            data.append(series.get(d, 0))
        return {'type': 'line', 'title': 'Ventas esta semana', 'labels': labels,
                'datasets': [{'label': 'Ventas ($)', 'data': data}]}

    if intent == 'month_sales':
        start = today - timedelta(days=29)
        # Agrupar por semana para no saturar
        series = dict(data_service.daily_series_since(restaurant_id, start))
        weeks = []
        week_start = start
        while week_start <= today:
            week_end = min(week_start + timedelta(days=6), today)
            week_total = sum(series.get(week_start + timedelta(days=i), 0)
                           for i in range((week_end - week_start).days + 1))
            label = f'{week_start.day}/{week_start.month}'
            weeks.append((label, week_total))
            week_start = week_end + timedelta(days=1)
        labels = [w[0] for w in weeks]
        data = [w[1] for w in weeks]
        return {'type': 'line', 'title': 'Ventas del mes', 'labels': labels,
                'datasets': [{'label': 'Ventas ($)', 'data': data}]}

    return None


def clean_chart(chart):
    """Sanea el objeto `chart` del LLM.

    El modelo puede devolver `datasets[].data` con valores no numéricos
    (p.ej. texto de sugerencias) o labels desalineadas. Aquí nos aseguramos
    de que `data` sea solo numérico y de que labels/series tengan longitud
    coherente, para que Chart.js no falle al renderizar.
    """
    if not isinstance(chart, dict):
        return None
    ctype = chart.get('type')
    if ctype not in VALID_CHART_TYPES:
        ctype = 'line'

    labels = chart.get('labels')
    labels = [str(l) for l in labels] if isinstance(labels, list) else []

    raw_datasets = chart.get('datasets') if isinstance(chart.get('datasets'), list) else []
    datasets = []
    for ds in raw_datasets:
        if not isinstance(ds, dict):
            continue
        raw_data = ds.get('data') if isinstance(ds.get('data'), list) else []
        data = []
        for v in raw_data:
            try:
                num = float(v)
            except (TypeError, ValueError):
                continue
            if num != num:  # NaN
                continue
            data.append(num)
        datasets.append({
            'label': str(ds.get('label') or f'Serie {len(datasets) + 1}'),
            'data': data,
        })
    if not datasets:
        return None

    # Alinear labels con la serie más larga.
    max_len = max((len(d['data']) for d in datasets), default=0)
    if max_len and len(labels) != max_len:
        if len(labels) > max_len:
            labels = labels[:max_len]
        else:
            labels = labels + [str(i + 1) for i in range(len(labels), max_len)]

    return {
        'type': ctype,
        'title': str(chart.get('title') or ''),
        'labels': labels,
        'datasets': datasets,
    }


def followup_suggestions(cls=None, last_intent=None, stage=None, seen_intents=None, restaurant_id=None):
    """Chips contextuales según el último intent y el historial de la conversación."""
    return data_service.followup_suggestions(
        cls=cls, last_intent=last_intent, stage=stage, seen_intents=seen_intents,
        restaurant_id=restaurant_id,
    )

"""Ventas del Día / Caja del POS — vistas del Blueprint 'dashboard'.

Extraído VERBATIM de `dashboard.py` sin cambios de comportamiento (Etapa 3
del refactor orch-refine-code). Archivo hermano PLANO (no subpaquete:
los `from ..x` relativos cambiarían de significado un nivel más adentro).

UN solo Blueprint de nombre 'dashboard' (lo exige el guard CSRF de
`verduras/app_factory.py` y todos los `url_for('dashboard.*')`): este
módulo NO crea Blueprint propio; reutiliza `dashboard_bp` y `dashboard.py`
lo importa al FINAL (ciclo parcial seguro porque el Blueprint ya está
definido). Los nombres de función de vista están INTACTOS (son los
endpoint names). Los imports `Decimal` y `caja_service` se conservan como
imports LOCALES dentro de cada función, igual que en el código original.
"""
from datetime import datetime, timedelta

from flask import jsonify, redirect, render_template, request, url_for

from ..services.pos_auth import current_pos_business
from .dashboard import dashboard_bp


@dashboard_bp.route('/pos/<slug>/ventas', methods=['GET'])
def pos_ventas(slug: str):
    """Pantalla de ventas del día + control de caja.

    Números del servicio caja (fuente única: lo que ve aquí y lo que firma
    el cierre es idéntico). Sin sesión o slug ajeno → login.
    """
    from decimal import Decimal

    from ..services import caja as caja_service

    business = current_pos_business()
    if business is None or business.slug != slug:
        return redirect(url_for('dashboard.pos_login'))
    today = caja_service.bogota_today()
    # Día consultado (?day=YYYY-MM-DD): inválido → hoy; futuro → hoy
    # (no hay ventas futuras que ver). Ayer y atrás, bienvenidos.
    day = today
    raw_day = (request.args.get('day') or '').strip()
    if raw_day:
        try:
            parsed = datetime.strptime(raw_day, '%Y-%m-%d').date()
            if parsed <= today:
                day = parsed
        except ValueError:
            pass
    day_sales = caja_service.day_sales(business.id, day)
    preview = caja_service.build_close_preview(business.id, day)
    movs = preview.get('movimientos', {})
    cierre = caja_service.get_cierre(business.id, day)

    total = preview['total']
    methods = preview['by_method']
    kg_by_product = {}
    for s in day_sales:
        for it in s.items:
            if (it.unit or '').lower() in ('kg', 'g', 'lb'):
                qty = float(it.quantity or 0)
                if (it.unit or '').lower() == 'lb':
                    qty *= 0.45359237
                elif (it.unit or '').lower() == 'g':
                    qty /= 1000.0
                row = kg_by_product.setdefault(
                    it.product_name, {'kg': 0.0, 'revenue': Decimal('0.00')})
                row['kg'] += qty
                row['revenue'] += it.line_total
    top5 = sorted(
        ({'name': k, **v} for k, v in kg_by_product.items()),
        key=lambda r: r['kg'], reverse=True)[:5]
    top_max = top5[0]['kg'] if top5 else 0

    def _fmt(value):
        return f'{float(value):,.0f}'.replace(',', '.')

    hourly = preview['hourly']
    peak_hour = max(range(24), key=lambda h: hourly[h])

    return render_template(
        'pos_ventas.html',
        business=business,
        today_label=day.strftime('%d/%m/%Y'),
        viewed_day=day.isoformat(),
        today_iso=today.isoformat(),
        yesterday_label=(today - timedelta(days=1)).isoformat(),
        kpis={
            'total': _fmt(total),
            'tickets': len(day_sales),
            'avg': _fmt(total / len(day_sales)) if day_sales else '0',
            'kg': f'{sum(r["kg"] for r in kg_by_product.values()):,.1f}'
                  .replace(',', '.'),
            'efectivo': _fmt(preview['cash_expected']),
        },
        breakdown=[
            {'key': k, 'total': _fmt(v['total']), 'count': v['count'],
             'pct': round(float(v['total']) / float(total) * 100, 1)
             if total else 0}
            for k, v in sorted(methods.items(),
                               key=lambda kv: kv[1]['total'], reverse=True)
        ],
        sales=[
            {'number': s.sale_number,
             'time': s.created_at.strftime('%H:%M'),
             'customer': s.customer_name or 'Cliente General',
             'items': [{'name': it.product_name,
                        'qty': str(it.quantity), 'unit': it.unit,
                        'total': _fmt(it.line_total)} for it in s.items],
             'method': s.payment_method,
             'total': _fmt(s.total)}
            for s in day_sales
        ],
        hourly=[float(h) for h in hourly],
        hourly_max=float(max(hourly)) if day_sales else 0,
        peak_hour=peak_hour,
        top5=top5,
        top_max=top_max,
        cierres_hist=[
            {'day': c.day, 'total': _fmt(c.total_sales),
             'expected': _fmt(c.cash_expected),
             'counted': _fmt(c.counted_cash),
             'difference': _fmt(c.difference)}
            for c in caja_service.recent_cierres(business.id, limit=7)
        ],
        cierre={
            'closed': cierre is not None,
            'expected': _fmt(preview['cash_expected']),
            'tickets': len(day_sales),
            'counted': _fmt(cierre.counted_cash) if cierre else None,
            'difference': _fmt(cierre.difference) if cierre else None,
            'ingresos': _fmt(movs.get('ingreso', 0)),
            'retiros': _fmt(movs.get('retiro', 0)),
        },
    )


@dashboard_bp.route('/pos/<slug>/ventas/movimiento', methods=['POST'])
def pos_ventas_movimiento(slug: str):
    """Asienta un ingreso/retiro de caja del día (sesión, sin roles)."""
    from ..services import caja as caja_service

    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        mov = caja_service.registrar_movimiento(
            business.id, data.get('tipo'), data.get('monto'),
            motivo=data.get('motivo'))
    except caja_service.CajaValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'movimiento_id': mov.id, 'tipo': mov.tipo,
        'monto': str(mov.monto),
    }), 201


@dashboard_bp.route('/pos/<slug>/ventas/cierre', methods=['POST'])
def pos_ventas_cierre(slug: str):
    """Firma el Cierre Z del día con el conteo físico del cajón.

    Duplicado del día → 400 (no se pisa). Contado inválido → 400.
    """
    from ..services import caja as caja_service

    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        cierre = caja_service.close_day(business.id,
                                        data.get('counted_cash'),
                                        day=data.get('day'))
    except caja_service.CajaValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'day': cierre.day,
        'total_sales': str(cierre.total_sales),
        'cash_expected': str(cierre.cash_expected),
        'counted_cash': str(cierre.counted_cash),
        'difference': str(cierre.difference),
    }), 201

"""Clientes / Fiados del POS — vistas del Blueprint 'dashboard'.

v2 (rediseño del panel, diseño Stitch): la página lleva KPIs derivados
(total por cobrar, abonos de hoy, compromisos, cupo), estado por cuenta
(al día / vencida / pagada) y teléfono listo para wa.me. La libreta gana
cupo de crédito y nota interna (ficha), y el abono registra su método.

UN solo Blueprint de nombre 'dashboard' (lo exige el guard CSRF de
`verduras/app_factory.py` y todos los `url_for('dashboard.*')`): este
módulo NO crea Blueprint propio; reutiliza `dashboard_bp` y `dashboard.py`
lo importa al FINAL (ciclo parcial seguro porque el Blueprint ya está
definido). Los nombres de función de vista están INTACTOS (son los
endpoint names). Los imports locales `clientes_svc` se conservan dentro
de cada función para minimizar el diff.
"""
import re
from datetime import date
from decimal import Decimal

from flask import jsonify, redirect, render_template, request, url_for

from ..services import sales as sales_service
from .dashboard import dashboard_bp
from .dashboard_helpers import _fmt_cop, _fmt_short, _pos_clientes_guard

_PHONE_DIGITS_RE = re.compile(r'\D+')


def _wa_phone(phone) -> str | None:
    """Teléfono normalizado para wa.me (57 + 10 dígitos) o None.

    Acepta '+57 312 300 0887', '3123000887', etc. Sin país se asume 57
    (Colombia, único mercado del módulo). Menos de 10 dígitos → None
    (número incompleto: mejor sin botón que un wa roto).
    """
    digits = _PHONE_DIGITS_RE.sub('', str(phone or ''))
    if not digits:
        return None
    if digits.startswith('57'):
        digits = digits[2:]
    if len(digits) < 10:
        return None
    return '57' + digits


@dashboard_bp.route('/pos/<slug>/clientes/buscar', methods=['GET'])
def pos_clientes_buscar(slug: str):
    """Buscador para el selector del POS (coincide nombre o teléfono)."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    q = (request.args.get('q') or '').strip().lower()
    rows = clientes_svc.list_clientes(business.id)
    if q:
        rows = [r for r in rows
                if q in r['name'].lower()
                or q in (r['phone'] or '').replace(' ', '')]
    for r in rows:
        r['saldo'] = _fmt_short(r['saldo'])
    return jsonify(success=True, data={'clientes': rows[:20]})


@dashboard_bp.route('/pos/<slug>/clientes', methods=['POST'])
def pos_clientes_crear(slug: str):
    """Crea (o reutiliza por nombre) un cliente desde el POS."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        existed = clientes_svc.VerdurasCliente.query.filter_by(
            business_id=business.id,
            name=(data.get('name') or '').strip()).first() is not None
        client = clientes_svc.get_or_create_client(
            business.id, data.get('name') or '',
            phone=data.get('phone'))
    except clientes_svc.ClientesValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'client_id': client.id, 'name': client.name,
        'phone': client.phone, 'created': not existed,
    })


@dashboard_bp.route('/pos/<slug>/clientes', methods=['GET'])
def pos_clientes_page(slug: str):
    """Pantalla Clientes / Fiados v2: KPIs, libretas con estado y cupo."""
    from ..services import clientes as clientes_svc
    from ..services.caja import bogota_today

    business = _pos_clientes_guard(slug)
    if business is None:
        return redirect(url_for('dashboard.pos_login'))
    cuentas = clientes_svc.list_clientes(business.id)
    resumen = clientes_svc.resumen_fiados(business.id, cuentas)
    hoy = bogota_today()
    hoy_iso = hoy.isoformat()

    for c in cuentas:
        saldo = Decimal(c['saldo'])
        limite = (Decimal(c['credit_limit'])
                  if c.get('credit_limit') is not None else None)
        compromiso = c.get('fecha_compromiso')
        # Estado (la "semaforización" de la libreta): vencida SOLO si
        # sigue debiendo y el compromiso ya pasó. Sin compromiso no hay
        # vencimiento posible → al día.
        if saldo <= 0:
            c['estado'] = 'pagada'
        elif compromiso and compromiso < hoy_iso:
            c['estado'] = 'vencida'
        else:
            c['estado'] = 'al_dia'
        dias = None
        if compromiso and c['estado'] == 'vencida':
            dias = (hoy - date.fromisoformat(compromiso)).days
        c['compromiso_display'] = (date.fromisoformat(
            compromiso).strftime('%d/%m/%Y') if compromiso else None)
        c['dias_atraso'] = dias
        c['saldo_fmt'] = _fmt_cop(saldo)
        c['credit_limit_fmt'] = _fmt_cop(limite) if limite is not None else None
        c['wa_phone'] = _wa_phone(c.get('phone'))

    uso_pct = 0
    if resumen['cupo_total']:
        uso_pct = round(float(
            resumen['uso_cupo'] / resumen['cupo_total'] * 100), 1)

    return render_template(
        'pos_clientes.html',
        business=business,
        cuentas=cuentas,
        kpis={
            'total_cobrar': _fmt_short(resumen['total_por_cobrar']),
            'con_saldo': resumen['con_saldo'],
            'abonos_hoy': _fmt_short(resumen['abonos_hoy']),
            'al_dia': resumen['al_dia'],
            'vencidas': resumen['vencidas'],
            'cupo_total': _fmt_short(resumen['cupo_total'])
            if resumen['cupo_total'] else None,
            'uso_cupo': _fmt_short(resumen['uso_cupo']),
            'uso_pct': uso_pct,
        },
        today_iso=hoy_iso,
    )


@dashboard_bp.route('/pos/<slug>/clientes/<int:client_id>', methods=['GET'])
def pos_clientes_detalle(slug: str, client_id: int):
    """Ficha de la cuenta: saldo/cupo, timeline fiados−abonos y wa.me."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    try:
        client = clientes_svc.require_client(business.id, client_id)
        saldo_dec = clientes_svc.saldo_cliente(business.id, client_id)
        tickets = sales_service.list_sales(business.id)
        tickets = [s for s in tickets
                   if s.client_id == client_id
                   and (s.payment_method or '') == 'libreta'
                   and s.status != 'cancelled'][:20]
        abonos = clientes_svc.VerdurasAbono.query.filter_by(
            business_id=business.id, client_id=client_id).order_by(
            clientes_svc.VerdurasAbono.registered_at.desc(),
            clientes_svc.VerdurasAbono.id.desc()).limit(20).all()
    except clientes_svc.ClientesNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404

    # Timeline unificado (la libreta mezcla cargos '+' y abonos '−').
    timeline = []
    for s in tickets:
        desc = ', '.join(
            f'{i.product_name} ({i.quantity.normalize()} {i.unit})'
            for i in s.items) or 'Venta a fiado'
        timeline.append({
            'kind': 'cargo', 'number': s.sale_number,
            'amount': _fmt_cop(s.total), 'raw': str(s.total),
            'description': desc[:140],
            'at': s.created_at.isoformat() if s.created_at else None,
        })
    for a in abonos:
        timeline.append({
            'kind': 'abono', 'number': None, 'amount': _fmt_cop(a.monto),
            'raw': str(a.monto), 'method': a.method,
            'note': a.note,
            'at': a.registered_at.isoformat() if a.registered_at else None,
        })
    timeline.sort(key=lambda m: m['at'] or '', reverse=True)

    limite = client.credit_limit
    disponible = None
    if limite is not None:
        disponible = max(limite - saldo_dec, Decimal('0.00'))
    uso_pct = None
    if limite is not None and limite > 0:
        uso_pct = min(round(float(saldo_dec / limite * 100), 1), 100.0)

    return jsonify(success=True, data={
        'client': {'id': client.id, 'name': client.name,
                   'phone': client.phone,
                   'fecha_compromiso': (
                       client.fecha_compromiso.isoformat()
                       if client.fecha_compromiso else None)},
        'saldo': _fmt_cop(saldo_dec),
        'saldo_raw': str(saldo_dec),
        'credit_limit': _fmt_cop(limite) if limite is not None else None,
        'disponible': _fmt_cop(disponible) if disponible is not None else None,
        'uso_pct': uso_pct,
        'internal_note': client.internal_note,
        'wa_phone': _wa_phone(client.phone),
        'timeline': timeline,
    })


@dashboard_bp.route('/pos/<slug>/clientes/<int:client_id>/ficha',
                    methods=['POST'])
def pos_clientes_ficha(slug: str, client_id: int):
    """Guarda cupo de crédito y nota interna de la libreta (v2)."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        # Updates parciales: solo las claves presentes (editar la nota no
        # pisa el cupo y viceversa).
        client = clientes_svc.require_client(business.id, client_id)
        if 'credit_limit' in data:
            client = clientes_svc.set_credit_limit(
                business.id, client_id, data.get('credit_limit'))
        if 'internal_note' in data:
            client = clientes_svc.set_internal_note(
                business.id, client_id, data.get('internal_note'))
    except clientes_svc.ClientesNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except clientes_svc.ClientesValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'client_id': client.id,
        'credit_limit': (str(client.credit_limit)
                         if client.credit_limit is not None else None),
        'internal_note': client.internal_note,
    })


@dashboard_bp.route('/pos/<slug>/clientes/<int:client_id>/abonar',
                    methods=['POST'])
def pos_clientes_abonar(slug: str, client_id: int):
    """Registra un abono contra la deuda (nunca mayor al saldo)."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        abono = clientes_svc.registrar_abono(
            business.id, client_id, data.get('monto'),
            note=data.get('note'), method=data.get('method'))
        saldo = clientes_svc.saldo_cliente(business.id, client_id)
    except clientes_svc.ClientesNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except clientes_svc.ClientesValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'abono_id': abono.id, 'monto': _fmt_cop(abono.monto),
        'method': abono.method,
        'saldo': _fmt_cop(saldo),
    }), 201


@dashboard_bp.route('/pos/<slug>/clientes/<int:client_id>/compromiso',
                    methods=['POST'])
def pos_clientes_compromiso(slug: str, client_id: int):
    """Guarda (o quita con null) la fecha de compromiso de la cuenta."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        client = clientes_svc.set_compromiso(
            business.id, client_id, data.get('fecha_compromiso'))
    except clientes_svc.ClientesNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except clientes_svc.ClientesValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'client_id': client.id,
        'fecha_compromiso': (client.fecha_compromiso.isoformat()
                             if client.fecha_compromiso else None),
    })

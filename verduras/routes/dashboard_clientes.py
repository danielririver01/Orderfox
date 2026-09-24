"""Clientes / Fiados del POS — vistas del Blueprint 'dashboard'.

Extraído VERBATIM de `dashboard.py` sin cambios de comportamiento (Etapa 2
del refactor orch-refine-code). Archivo hermano PLANO (no subpaquete:
los `from ..auth` relativos cambiarían de significado un nivel más adentro).

UN solo Blueprint de nombre 'dashboard' (lo exige el guard CSRF de
`verduras/app_factory.py` y todos los `url_for('dashboard.*')`): este
módulo NO crea Blueprint propio; reutiliza `dashboard_bp` y `dashboard.py`
lo importa al FINAL (ciclo parcial seguro porque el Blueprint ya está
definido). Los nombres de función de vista están INTACTOS (son los
endpoint names). Los imports locales `clientes_svc` se conservan dentro
de cada función para minimizar el diff.
"""
from flask import jsonify, redirect, render_template, request, url_for

from ..services import sales as sales_service
from .dashboard import dashboard_bp
from .dashboard_helpers import _fmt_short, _pos_clientes_guard


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
    """Pantalla Clientes / Fiados: cuentas con saldo, compromiso y abonos."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return redirect(url_for('dashboard.pos_login'))
    cuentas = clientes_svc.list_clientes(business.id)
    for c in cuentas:
        c['saldo'] = _fmt_short(c['saldo'])
    return render_template(
        'pos_clientes.html',
        business=business,
        cuentas=cuentas,
    )


@dashboard_bp.route('/pos/<slug>/clientes/<int:client_id>', methods=['GET'])
def pos_clientes_detalle(slug: str, client_id: int):
    """Detalle de la cuenta: cliente, saldo, tickets fiados y abonos."""
    from ..services import clientes as clientes_svc

    business = _pos_clientes_guard(slug)
    if business is None:
        return jsonify(success=False, error='sesion_expirada'), 401
    try:
        client = clientes_svc.require_client(business.id, client_id)
        saldo = _fmt_short(clientes_svc.saldo_cliente(business.id,
                                                      client_id))
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
    return jsonify(success=True, data={
        'client': {'id': client.id, 'name': client.name,
                   'phone': client.phone,
                   'fecha_compromiso': (
                       client.fecha_compromiso.isoformat()
                       if client.fecha_compromiso else None)},
        'saldo': str(saldo),
        'tickets': [{'number': s.sale_number, 'total': str(s.total),
                     'created_at': s.created_at.isoformat()
                     if s.created_at else None} for s in tickets],
        'abonos': [{'monto': str(a.monto),
                    'registered_at': a.registered_at.isoformat()
                    if a.registered_at else None,
                    'note': a.note} for a in abonos],
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
            note=data.get('note'))
        saldo = clientes_svc.saldo_cliente(business.id, client_id)
    except clientes_svc.ClientesNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except clientes_svc.ClientesValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'abono_id': abono.id, 'monto': str(abono.monto),
        'saldo': str(saldo),
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

"""
Dashboard del tendero (POS) — Jinja2 + sesión, mismo patrón que core.

Rutas html (el tendero ve pantallas) y la acción de venta por sesión:
la SERVICE_API_KEY NUNCA llega al navegador. Las APIs JSON con x-api-key
quedan para integraciones server-to-server y el checkout público.
"""
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from ..auth import require_service_api_key
from app.services.insights import data_service_verduras as copilot_vd

from ..services import alerts as alerts_service
from ..services import catalog
from ..services import inventory as inventory_service
from ..services import context as context_service
from ..services import pos_auth as pos_auth_service
from ..services import sales as sales_service
from ..services import scale as scale_service
from ..services.pos_auth import (
    PosAuthError,
    consume_pos_sso_token,
    current_pos_business,
    login_pos,
    logout_pos,
    request_pos_pin_reset,
    require_pos_business,
    setup_pos_pin,
)
from .dashboard_helpers import (
    _fmt_cop,
    _fmt_short,
    _sale_for_ticket,
)

dashboard_bp = Blueprint('dashboard', __name__)


# ── Login / sesión ──────────────────────────────────────────


@dashboard_bp.route('/pos', methods=['GET'])
def pos_home():
    business = current_pos_business()
    if business:
        return redirect(url_for('dashboard.pos_view', slug=business.slug))
    return redirect(url_for('dashboard.pos_login'))


@dashboard_bp.route('/pos/login', methods=['GET', 'POST'])
def pos_login():
    if request.method == 'POST':
        identifier = request.form.get('identifier') or request.form.get('slug')
        try:
            business = login_pos(
                identifier,
                request.form.get('pin'),
                ip=request.remote_addr,
            )
        except PosAuthError as e:
            flash(str(e), 'error')
            return render_template('pos_login.html'), 401
        return redirect(url_for('dashboard.pos_view', slug=business.slug))
    return render_template('pos_login.html')


@dashboard_bp.route('/pos/logout', methods=['POST'])
def pos_logout():
    logout_pos()
    return redirect(url_for('dashboard.pos_login'))


@dashboard_bp.route('/pos/forgot-pin', methods=['GET', 'POST'])
def pos_forgot_pin():
    """Pantalla para solicitar restablecimiento del PIN del POS por correo."""
    if request.method == 'POST':
        email = request.form.get('email')
        _ok, message = request_pos_pin_reset(
            email, base_url=request.host_url.rstrip('/'))
        flash(message, 'ok')
        return redirect(url_for('dashboard.pos_login'))
    return render_template('pos_forgot_pin.html')


@dashboard_bp.route('/api/verduras/businesses/<int:business_id>/pos-pin',
                    methods=['POST'])
def api_setup_pos_pin(business_id: int):
    """Configura el PIN del POS (onboarding, server-to-server con x-api-key).

    Deliberadamente NO es una pantalla pública: permitir que cualquiera
    cree el "primer PIN" sabiendo el slug sería business squatting. El
    dashboard de core (o el provisioner) llama aquí con la service key.
    """
    try:
        require_service_api_key()
    except Exception:  # noqa: BLE001 — VerdurasAuthError es PermissionError
        return jsonify(success=False, error_code='unauthorized'), 401
    from ..services.pos_auth import PosAuthError as _PAE
    try:
        setup_pos_pin(business_id, (request.get_json(silent=True) or {}).get('pin'))
    except _PAE as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, message='PIN del POS configurado')


# ── Setup del POS con token de un solo uso (registro self-service) ──


@dashboard_bp.route('/pos/setup/<slug>/<token>', methods=['GET'])
def pos_setup_form(slug: str, token: str):
    """Pantalla de primer setup: el dueño llega desde el registro de core.

    Pre-auth POR DISEÑO: el enlace firmado en DB es la credencial (un solo
    uso). El POST igual pasa por el guard CSRF de la factory.
    """
    try:
        business = pos_auth_service.get_setup_target(slug, token)
    except PosAuthError as e:
        flash(str(e), 'error')
        return redirect(url_for('dashboard.pos_login'))
    return render_template('pos_setup.html', business=business, token=token)


@dashboard_bp.route('/pos/setup/<slug>/<token>', methods=['POST'])
def pos_setup_submit(slug: str, token: str):
    """Consume el token: configura PIN + WhatsApp y deja el POS listo."""
    pin = request.form.get('pin')
    pin2 = request.form.get('pin2')
    if pin != pin2:
        flash('Los PIN no coinciden', 'error')
        return redirect(url_for('dashboard.pos_setup_form', slug=slug,
                                token=token))
    try:
        pos_auth_service.consume_setup_token(
            slug, token, pin,
            whatsapp_phone=request.form.get('whatsapp_phone'))
    except PosAuthError as e:
        flash(str(e), 'error')
        return redirect(url_for('dashboard.pos_setup_form', slug=slug,
                                token=token))
    flash('¡Listo! Tu POS quedó configurado. Entra con tu PIN.', 'ok')
    return redirect(url_for('dashboard.pos_login'))


# ── Handoff Mundos → POS (dueño llega sin PIN) ──────────────


@dashboard_bp.route('/pos/sso/<slug>/<token>', methods=['GET'])
def pos_sso(slug: str, token: str):
    """Consume el handoff emitido por core y abre la sesión del POS.

    Pre-auth POR DISEÑO (igual que el setup): el bearer de 256 bits, de un
    solo uso y con expiración de 5 min ES la credencial. Enlace muerto o
    reusado → login de mostrador con mensaje genérico.
    """
    try:
        business = consume_pos_sso_token(slug, token)
    except PosAuthError as e:
        flash(str(e), 'error')
        return redirect(url_for('dashboard.pos_login'))
    return redirect(url_for('dashboard.pos_view', slug=business.slug))


# ── Pantallas ───────────────────────────────────────────────


@dashboard_bp.route('/pos/<slug>', methods=['GET'])
def pos_view(slug: str):
    business = current_pos_business()
    if business is None or business.slug != slug:
        return redirect(url_for('dashboard.pos_login'))
    # Ciclo de suscripción: el tendero ve el estado (vence pronto / gracia) o
    # una pantalla de renovación si ya no puede vender. Jamás un 500.
    try:
        sub = context_service.get_subscription_status(business)
    except Exception:  # noqa: BLE001 — la suscripción jamás tumba el POS
        sub = {'can_crud': True}
    if not sub.get('can_crud'):
        core_base = current_app.config.get('CORE_BASE_URL') or 'http://localhost:5000'
        return render_template(
            'pos_renewal.html', business=business, status=sub,
            core_payment_url=f'{core_base}/renew',
        )
    products = catalog.list_products(business.id)
    # Mapa product_id → severidad de alerta de rotación (Semana 5): el POS
    # pinta un badge por producto, informativo — nunca bloquea la venta.
    try:
        alerts_map = {
            str(a['product_id']): a['severity']
            for a in alerts_service.list_alerts(business.id)['alerts']
        }
    except Exception:  # noqa: BLE001 — las alertas jamás tumban el POS
        alerts_map = {}
    pos_data = {
        'scale_enabled': bool(current_app.config.get('SCALE_ENABLED', False)),
        'alerts': alerts_map,
        'products': [
            {
                'id': p.id,
                'name': p.name,
                'unit': p.unit,
                'price': str(p.current_price),
                'category_id': p.category_id,
            }
            for p in products
        ],
    }
    return render_template(
        'pos.html',
        business=business,
        categories=catalog.list_categories(business.id),
        pos_settings=sales_service.get_settings(business.id),
        pos_data=pos_data,
        pos_urls={
            'sell': url_for('dashboard.pos_sell', slug=business.slug),
            'scale': url_for('dashboard.pos_scale_weight', slug=business.slug),
        },
    )


# ── Inventario y Precios (sesión del tendero, sin x-api-key) ──


@dashboard_bp.route('/pos/<slug>/inventario', methods=['GET'])
def pos_inventory(slug: str):
    """Pantalla de inventario: tabla con stock/precio/estado + KPIs reales.

    Una sola pasada de ensamblado (sin N+1 visible): productos + mapa de
    stock + alertas. Sin sesión o slug ajeno → login (mismo guard que el POS).
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return redirect(url_for('dashboard.pos_login'))
    stock_rows = inventory_service.list_stock(business.id)
    # La tabla MUESTRA inactivos con su badge (el POS los oculta con su
    # propio query). Sin esto el badge "Inactivo" era inalcanzable.
    stock_map = {str(r['product_id']): r for r in stock_rows}
    try:
        alerts_map = {
            str(a['product_id']): a['severity']
            for a in alerts_service.list_alerts(business.id)['alerts']
        }
    except Exception:  # noqa: BLE001 — las alertas jamás tumban la vista
        alerts_map = {}
    inv_value = sum(
        (float(r['stock_value']) for r in stock_rows if r['stock_value']),
        0.0,
    )
    # ── Paneles Copilot en MODO LECTURA (Fase 3, cero tokens de IA) ──
    # Puro cálculo SQL del adapter; si algo falla, el panel se oculta —
    # jamás tumban la tabla.
    products_by_name = {p.name: p for p in catalog.list_products(business.id)}

    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:  # noqa: BLE001 — paneles nunca tumban la vista
            return default

    # Actividad en idioma de mostrador (no códigos): la arma el feed
    # unificado; si falla, lista vacía (el panel muestra su vacío honesto).
    actividad = _safe(
        lambda: inventory_service.activity_feed(business.id, limit=8),
        default=[])
    margin = _safe(lambda: copilot_vd.margins(business.id, days=30))
    if margin and margin.get('items'):
        # El adapter devuelve crudos (3195, '3200.00'): formatear para ojos.
        margin['totals'] = {**margin.get('totals', {}),
                            'margin': _fmt_short(margin['totals']['margin']),
                            'revenue': _fmt_short(margin['totals']['revenue'])}
        for _it in margin['items']:
            _it['margin'] = _fmt_short(_it['margin'])
    restock = _safe(lambda: copilot_vd.restock_suggestions(business.id))
    reco_items = []
    if restock:
        for it in [i for i in restock.get('items', [])
                   if i.get('suggested', 0) > 0][:5]:
            prod = products_by_name.get(it['name'])
            if prod is None:
                continue
            reco_items.append({
                'product_id': prod.id, 'name': it['name'],
                'unit': it['unit'], 'stock': it['stock'],
                'suggested': it['suggested'],
                'min_stock': (str(prod.min_stock)
                              if prod.min_stock is not None else ''),
            })
    categories = catalog.list_categories(business.id)
    from sqlalchemy import func as _func
    from verduras.models import VerdurasProduct as _VP
    cat_counts = dict(
        catalog.db.session.query(
            _VP.category_id, _func.count(_VP.id))
        .filter(_VP.business_id == business.id)
        .group_by(_VP.category_id).all()
    )
    return render_template(
        'pos_inventory.html',
        business=business,
        categories=categories,
        cat_counts=cat_counts,
        inv_rows=[
            {
                'id': p.id,
                'name': p.name,
                'unit': p.unit,
                'price': str(p.current_price),
                'price_fmt': _fmt_cop(p.current_price),
                'category_id': p.category_id,
                'is_active': bool(p.is_active),
                'stock': (stock_map.get(str(p.id)) or {}).get('stock'),
                'alert': alerts_map.get(str(p.id)),
            }
            for p in catalog.list_products(business.id,
                                              include_inactive=True)
        ],
        inv_kpis={
            'value': inv_value,
            'count': len(stock_rows),
            'alerts': len(alerts_map),
        },
        actividad=actividad,
        margin=margin if margin and margin.get('items') else None,
        reco_items=reco_items,
    )


@dashboard_bp.route('/pos/<slug>/inventario/minimo', methods=['POST'])
def pos_inventory_minimum(slug: str):
    """Ajusta el mínimo de alerta desde la recomendación (sesión, sin roles).

    Usa alerts.set_min_stock (business-scoped: producto ajeno → 404).
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        product = alerts_service.set_min_stock(
            business.id, data.get('product_id'), data.get('min_stock'))
    except LookupError as e:
        return jsonify(success=False, error=str(e)), 404
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'product_id': product.id,
        'min_stock': (str(product.min_stock)
                      if product.min_stock is not None else None),
    })


@dashboard_bp.route('/pos/<slug>/inventario/precio', methods=['POST'])
def pos_inventory_price(slug: str):
    """Precio inline de la tabla (sesión del tendero, sin roles en v1).

    Usa catalog.update_price: valida, guarda y deja historial. 400 ante
    precio inválido/igual, 404 ante producto ajeno.
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        product = catalog.update_price(
            business.id, data.get('product_id'), data.get('price'))
    except catalog.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except catalog.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True,
                   data={'product_id': product.id,
                         'price': str(product.current_price)})


@dashboard_bp.route('/pos/<slug>/inventario/editar', methods=['POST'])
def pos_inventory_edit(slug: str):
    """Edita ficha del producto (nombre/categoría/activo). Unidad y stock
    NO editables por diseño (ver catalog.update_product)."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        category_id = data.get('category_id')
        if not category_id and (data.get('category_name') or '').strip():
            category = catalog.create_category(
                business.id, data['category_name'].strip())
            category_id = category.id
        product = catalog.update_product(
            business.id, data.get('product_id'),
            name=(data.get('name') if 'name' in data else None),
            category_id=category_id,
            is_active=(data.get('is_active')
                       if 'is_active' in data else None),
        )
    except catalog.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except catalog.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'product_id': product.id, 'name': product.name,
        'unit': product.unit, 'price': str(product.current_price),
        'category_id': product.category_id,
        'is_active': bool(product.is_active),
    })


@dashboard_bp.route('/pos/<slug>/inventario/lote', methods=['POST'])
def pos_inventory_lot(slug: str):
    """Registra compra (lote): sube stock y fija costo (sesión, sin roles).

    El costo es TOTAL del lote (unitario = total/cantidad, lo deriva el
    servicio). Sin lotes no hay stock ni costo: por eso todo es 0.000.
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        lot = inventory_service.register_lot(
            business.id, data.get('product_id'),
            data.get('quantity'), data.get('total_cost'))
    except LookupError as e:
        return jsonify(success=False, error=str(e)), 404
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'lot_id': lot.id, 'quantity': str(lot.quantity),
        'total_cost': str(lot.total_cost),
    }), 201


@dashboard_bp.route('/pos/<slug>/inventario/merma', methods=['POST'])
def pos_inventory_merma(slug: str):
    """Registra merma (pérdida): baja stock con pérdida congelada en COP."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        merma = inventory_service.register_merma(
            business.id, data.get('product_id'),
            data.get('quantity'), reason=data.get('reason', 'danado'))
    except LookupError as e:
        return jsonify(success=False, error=str(e)), 404
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'merma_id': merma.id, 'quantity': str(merma.quantity),
        'cost_loss': str(merma.cost_loss),
    }), 201


@dashboard_bp.route('/pos/<slug>/inventario/eliminar', methods=['POST'])
def pos_inventory_delete(slug: str):
    """Elimina un producto = lo desactiva (soft delete, punto fuerte del
    modal: acción irreversible en pantalla). El historial NUNCA se toca:
    ventas e items guardan snapshot y la FK no se rompe. Sin roles en v1.
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        product = catalog.update_product(
            business.id, data.get('product_id'), is_active=False)
    except catalog.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except catalog.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True,
                   data={'product_id': product.id,
                         'is_active': bool(product.is_active)})


@dashboard_bp.route('/pos/<slug>/inventario/categoria/renombrar',
                   methods=['POST'])
def pos_inventory_rename_category(slug: str):
    """Renombra una categoría (siempre seguro: no toca FKs ni historial)."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        category = catalog.rename_category(
            business.id, data.get('category_id'), data.get('name') or '')
    except catalog.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except catalog.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True,
                   data={'category_id': category.id,
                         'name': category.name})


@dashboard_bp.route('/pos/<slug>/inventario/categoria/eliminar',
                    methods=['POST'])
def pos_inventory_delete_category(slug: str):
    """Elimina una categoría; con productos exige destino (los mueve en la
    misma transacción). Sin destino y con productos → 400 con conteo."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        result = catalog.delete_category(
            business.id, data.get('category_id'),
            move_to_category_id=data.get('move_to_category_id'))
    except catalog.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except catalog.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data=result)


@dashboard_bp.route('/pos/<slug>/inventario/ajuste', methods=['POST'])
def pos_inventory_ajuste(slug: str):
    """Corrección de stock FIRMADA por conteo físico (sesión, sin roles).

    El dueño ingresa lo CONTADO; el backend calcula la diferencia contra
    el sistema. Delta cero o contado negativo → 400 (no hay nada que
    corregir / dato imposible).
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        ajuste = inventory_service.register_ajuste(
            business.id, data.get('product_id'),
            data.get('counted'), motivo=data.get('motivo', 'conteo'),
            note=data.get('note'))
    except LookupError as e:
        return jsonify(success=False, error=str(e)), 404
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'ajuste_id': ajuste.id,
        'stock_before': str(ajuste.stock_before),
        'counted': str(ajuste.counted),
        'delta': str(ajuste.delta),
        'motivo': ajuste.motivo,
    }), 201


@dashboard_bp.route('/pos/<slug>/inventario/producto', methods=['POST'])
def pos_inventory_product(slug: str):
    """Nuevo producto desde el POS (sesión del tendero, sin roles en v1).

    Categoría existente (id) o nueva por nombre (se crea al vuelo).
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        from verduras.models import VerdurasProduct as _VP
        prior = _VP.query.filter_by(
            business_id=business.id,
            name=(data.get('name') or '').strip()).first()
        was_inactive = bool(prior is not None and not prior.is_active)
        category_id = data.get('category_id')
        if not category_id and (data.get('category_name') or '').strip():
            category = catalog.create_category(
                business.id, data['category_name'].strip())
            category_id = category.id
        product = catalog.create_product(
            business.id, category_id,
            data.get('name') or '', data.get('unit') or '',
            data.get('price'))
    except catalog.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    except catalog.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'product_id': product.id, 'name': product.name,
        'unit': product.unit, 'price': str(product.current_price),
        'category_id': product.category_id,
        # Recrear un desactivado = reactivarlo (visible, con historial).
        'reactivated': bool(was_inactive and prior.id == product.id),
    }), 201


# ── Ventas del Día (sesión del tendero, sin x-api-key) ───────


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


# ── Acciones del POS (sesión, sin x-api-key) ────────────────


@dashboard_bp.route('/pos/<slug>/sell', methods=['POST'])
def pos_sell(slug: str):
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    # Segundo candado: la sesión puede seguir viva aunque la suscripción
    # haya vencido — la venta exige can_crud (mismo criterio del gate de pos_view).
    try:
        sub = context_service.get_subscription_status(business)
    except Exception:  # noqa: BLE001 — la suscripción jamás tumba el POS
        sub = {'can_crud': True}
    if not sub.get('can_crud'):
        return (jsonify(success=False, error='suscripcion_inactiva',
                        message=sub.get('message')), 409)
    data = request.get_json(silent=True) or {}
    try:
        sale, _created = sales_service.create_sale(
            business.id,
            data.get('items') or [],
            sale_type='walk_in',
            customer_name=data.get('customer_name') or '',
            payment_method=data.get('payment_method'),
            amount_received=data.get('amount_received'),
            client_id=data.get('client_id'),
            skip_open_check=True,  # venta de mostrador aunque esté "cerrado"
        )
    except sales_service.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    except sales_service.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    return jsonify(success=True, data=_sale_for_ticket(sale))


# ── Báscula digital (Semana 4) ──────────────────────────────


@dashboard_bp.route('/pos/<slug>/api/scale/weight', methods=['GET'])
def pos_scale_weight(slug: str):
    """Lee la báscula del POS (sesión del tendero; sin x-api-key).

    Nunca devuelve 500: cualquier problema de báscula es un 409 con código
    legible para el frontend, que pide ingreso manual y la venta continúa.
    La báscula es ayuda, no requisito.
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    try:
        weight = scale_service.read_weight(
            enabled=current_app.config.get('SCALE_ENABLED', False),
            protocol=current_app.config.get('SCALE_PROTOCOL', 'generic'),
            port=current_app.config.get('SCALE_PORT', 'COM3'),
            baudrate=current_app.config.get('SCALE_BAUDRATE', 9600),
            timeout_s=current_app.config.get('SCALE_TIMEOUT_S', 2.0),
        )
    except scale_service.ScaleDisabledError:
        return jsonify(success=False, error_code='scale_disabled',
                       error='La báscula no está activada en este negocio'), 409
    except scale_service.ScaleUnavailableError as e:
        return jsonify(success=False, error_code='scale_unavailable',
                       error=str(e)), 409
    except scale_service.ScaleReadError as e:
        return jsonify(success=False, error_code='scale_read_error',
                       error=str(e)), 409
    return jsonify(success=True, data={'weight_kg': weight})


# ── Submódulos del dashboard (mismo Blueprint 'dashboard') ──
# Import al FINAL: dashboard_clientes hace `from .dashboard import
# dashboard_bp` (ciclo parcial seguro — el Blueprint ya está definido
# arriba). Los nombres de función de vista se conservan intactos.
from . import dashboard_clientes  # noqa: F401

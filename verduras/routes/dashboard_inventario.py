"""Inventario y Precios del POS — vistas del Blueprint 'dashboard'.

Extraído VERBATIM de `dashboard.py` sin cambios de comportamiento (Etapa 4
del refactor orch-refine-code). Archivo hermano PLANO (no subpaquete:
los `from ..x` relativos cambiarían de significado un nivel más adentro).

UN solo Blueprint de nombre 'dashboard' (lo exige el guard CSRF de
`verduras/app_factory.py` y todos los `url_for('dashboard.*')`): este
módulo NO crea Blueprint propio; reutiliza `dashboard_bp` y `dashboard.py`
lo importa al FINAL (ciclo parcial seguro porque el Blueprint ya está
definido). Los nombres de función de vista están INTACTOS (son los
endpoint names). Los imports locales (`sqlalchemy.func`, `VerdurasProduct`)
se conservan dentro de cada función, igual que en el código original.
"""
from flask import jsonify, redirect, render_template, request, url_for

from app.services.insights import data_service_verduras as copilot_vd

from ..services import alerts as alerts_service
from ..services import catalog
from ..services import inventory as inventory_service
from ..services.pos_auth import current_pos_business
from .dashboard import dashboard_bp
from .dashboard_helpers import _fmt_cop, _fmt_short


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

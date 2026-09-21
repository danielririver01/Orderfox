"""
API JSON de inventario y merma Verduras (Semana 3).

Auth: TODO el inventario es dato privado del negocio (costos, stock,
pérdidas) → todas las rutas exigen header `x-api-key` contra
SERVICE_API_KEY (lo llama el dashboard del tendero, patrón de core).

Scoping: todos los endpoints exigen `business_id` explícito; el servicio
valida pertenencia (anti-IDOR) y el producto ajeno responde 404.
"""
from flask import Blueprint, jsonify, request

from ..auth import VerdurasAuthError, require_service_api_key
from ..services.alerts import list_alerts, set_min_stock
from ..services.context import (
    BusinessNotFoundError,
    BusinessNotVegetalError,
    require_business,
)
from ..services.inventory import (
    VerdurasNotFoundError,
    VerdurasValidationError,
    get_stock,
    list_lots,
    list_merma,
    list_stock,
    merma_report,
    register_lot,
    register_merma,
)

inventory_bp = Blueprint('inventory', __name__, url_prefix='/api/verduras')


def _business_or_error(business_id):
    try:
        return require_business(business_id), None
    except BusinessNotFoundError:
        return None, (jsonify(success=False, error_code='business_not_found'), 404)
    except BusinessNotVegetalError as e:
        return None, (jsonify(success=False, error_code='business_not_available',
                              message=str(e)), 409)


def _api_key_or_error():
    try:
        require_service_api_key()
        return None
    except VerdurasAuthError as e:
        return jsonify(success=False, error_code='unauthorized', message=str(e)), 401


def _error_response(e: Exception):
    if isinstance(e, VerdurasNotFoundError):
        return jsonify(success=False, error_code='not_found', message=str(e)), 404
    return jsonify(success=False, error_code='validation_error', message=str(e)), 400


def _lot_dict(lot) -> dict:
    return {
        'id': lot.id,
        'product_id': lot.product_id,
        'quantity': str(lot.quantity),
        'total_cost': str(lot.total_cost),
        'unit_cost': str(lot.unit_cost) if lot.unit_cost is not None else None,
        'purchased_at': lot.purchased_at.isoformat() if lot.purchased_at else None,
        'note': lot.note,
    }


def _merma_dict(m) -> dict:
    return {
        'id': m.id,
        'product_id': m.product_id,
        'quantity': str(m.quantity),
        'reason': m.reason,
        'cost_loss': str(m.cost_loss),
        'registered_at': m.registered_at.isoformat() if m.registered_at else None,
        'note': m.note,
    }


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ── Stock derivado ──────────────────────────────────────────


@inventory_bp.route('/businesses/<int:business_id>/inventory', methods=['GET'])
def get_inventory(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        stock = list_stock(biz.id, until=request.args.get('until'))
    except VerdurasValidationError as e:
        return _error_response(e)
    return jsonify(success=True, data={'stock': stock})


@inventory_bp.route('/businesses/<int:business_id>/inventory/<int:product_id>',
                    methods=['GET'])
def get_product_stock(business_id: int, product_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        return jsonify(success=True,
                       data=get_stock(biz.id, product_id,
                                      until=request.args.get('until')))
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)


# ── Lotes de compra ─────────────────────────────────────────


@inventory_bp.route('/businesses/<int:business_id>/inventory/lots',
                    methods=['POST'])
def post_lot(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    data = _body()
    try:
        lot = register_lot(
            biz.id,
            data.get('product_id'),
            data.get('quantity'),
            data.get('total_cost'),
            purchased_at=data.get('purchased_at'),
            note=data.get('note'),
        )
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_lot_dict(lot)), 201


@inventory_bp.route('/businesses/<int:business_id>/inventory/lots',
                    methods=['GET'])
def get_lots(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    lots = list_lots(
        biz.id,
        product_id=request.args.get('product_id', type=int),
        limit=request.args.get('limit', type=int) or 100,
    )
    return jsonify(success=True, data={'lots': [_lot_dict(l) for l in lots]})


# ── Merma ───────────────────────────────────────────────────


@inventory_bp.route('/businesses/<int:business_id>/inventory/merma',
                    methods=['POST'])
def post_merma(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    data = _body()
    try:
        merma = register_merma(
            biz.id,
            data.get('product_id'),
            data.get('quantity'),
            reason=data.get('reason'),
            note=data.get('note'),
            unit_cost=data.get('unit_cost'),
        )
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_merma_dict(merma)), 201


@inventory_bp.route('/businesses/<int:business_id>/inventory/merma',
                    methods=['GET'])
def get_merma(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        rows = list_merma(
            biz.id,
            product_id=request.args.get('product_id', type=int),
            day_from=request.args.get('date_from'),
            day_to=request.args.get('date_to'),
        )
    except VerdurasValidationError as e:
        return _error_response(e)
    return jsonify(success=True, data={'merma': [_merma_dict(m) for m in rows]})


@inventory_bp.route('/businesses/<int:business_id>/inventory/merma/report',
                    methods=['GET'])
def get_merma_report(business_id: int):
    """Reporte semanal/mensual: pérdida por producto, % y compras del período."""
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        report = merma_report(
            biz.id,
            request.args.get('date_from'),
            request.args.get('date_to'),
        )
    except VerdurasValidationError as e:
        return _error_response(e)
    return jsonify(success=True, data=report)


# ── Alertas de rotación (Semana 5) ──────────────────────────


@inventory_bp.route('/businesses/<int:business_id>/inventory/alerts',
                    methods=['GET'])
def get_alerts(business_id: int):
    """Alertas activas (stock <= umbral): severidad, días restantes y mensaje."""
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        return jsonify(success=True, data=list_alerts(
            biz.id, until=request.args.get('until')))
    except VerdurasValidationError as e:
        return _error_response(e)


@inventory_bp.route(
    '/businesses/<int:business_id>/inventory/products/<int:product_id>/min-stock',
    methods=['POST'])
def post_min_stock(business_id: int, product_id: int):
    """Configura el umbral de alerta del producto (null = sin alerta)."""
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        product = set_min_stock(biz.id, product_id,
                                _body().get('min_stock'))
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data={
        'product_id': product.id,
        'min_stock': str(product.min_stock) if product.min_stock is not None
        else None,
    })

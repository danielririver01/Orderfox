"""
API JSON de ventas Verduras (Semana 2).

Auth (mismo patrón que catalog.py):
- Endpoints de POS/operación (settings, listar, transiciones): header
  `x-api-key` contra SERVICE_API_KEY — lo llama el dashboard del tendero
  server-to-server.
- Checkout público (POST /sales): abierto, protegido por honeypot +
  time-to-submit + rate limit + idempotencia (patrón de core).

Scoping: todos los endpoints exigen `business_id` explícito; el servicio
valida pertenencia (anti-IDOR) y vertical.
"""
from flask import Blueprint, jsonify, request

from ..auth import VerdurasAuthError, require_service_api_key
from ..services.context import (
    BusinessNotFoundError,
    BusinessNotVegetalError,
    require_business,
)
from ..services.sales import (
    VerdurasNotFoundError,
    VerdurasValidationError,
    build_whatsapp_link,
    check_public_guards,
    create_sale,
    get_sale,
    get_settings,
    list_sales,
    mark_cancelled,
    mark_completed,
    update_settings,
)

sales_bp = Blueprint('sales', __name__, url_prefix='/api/verduras')


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


def _sale_dict(sale, with_wa_link: bool = False) -> dict:
    data = {
        'id': sale.id,
        'sale_number': sale.sale_number,
        'sale_type': sale.sale_type,
        'customer_name': sale.customer_name,
        'customer_phone': sale.customer_phone,
        'delivery_address': sale.delivery_address,
        'total': str(sale.total),
        'status': sale.status,
        'created_at': sale.created_at.isoformat() if sale.created_at else None,
        'items': [
            {
                'product_id': i.product_id,
                'product_name': i.product_name,
                'unit': i.unit,
                'unit_price': str(i.unit_price),
                'quantity': str(i.quantity),
                'line_total': str(i.line_total),
            }
            for i in sale.items
        ],
    }
    if with_wa_link:
        link = build_whatsapp_link(sale.business_id, sale)
        data['whatsapp_link'] = link
    return data


def _settings_dict(s) -> dict:
    return {
        'business_id': s.business_id,
        'whatsapp_phone': s.whatsapp_phone,
        'is_open': s.is_open,
        'delivery_enabled': s.delivery_enabled,
    }


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ── Settings ────────────────────────────────────────────────


@sales_bp.route('/businesses/<int:business_id>/settings', methods=['GET'])
def get_business_settings(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    return jsonify(success=True, data=_settings_dict(get_settings(biz.id)))


@sales_bp.route('/businesses/<int:business_id>/settings', methods=['POST'])
def post_business_settings(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        row = update_settings(biz.id, _body())
    except VerdurasValidationError as e:
        return _error_response(e)
    return jsonify(success=True, data=_settings_dict(row))


# ── Ventas ──────────────────────────────────────────────────


@sales_bp.route('/businesses/<int:business_id>/sales', methods=['POST'])
def post_sale(business_id: int):
    """Checkout público (delivery) o POS walk-in del dashboard."""
    biz, err = _business_or_error(business_id)
    if err:
        return err

    data = _body()
    sale_type = (data.get('sale_type') or 'walk_in').strip().lower()

    # Guards anti-abuso SOLO para checkout público; el POS del tendero pasa
    # (pero exige API key: la venta de mostrador viene del dashboard).
    if sale_type == 'delivery':
        error, status = check_public_guards(data, biz.id, request.remote_addr)
        if error:
            return jsonify(error), status
    else:
        err = _api_key_or_error()
        if err:
            return err

    try:
        sale, created = create_sale(
            biz.id,
            data.get('items') or [],
            sale_type=sale_type,
            customer_name=data.get('customer_name') or '',
            customer_phone=data.get('customer_phone') or '',
            delivery_address=data.get('delivery_address'),
            idempotency_key=data.get('idempotency_key'),
            ip_address=request.remote_addr,
            skip_open_check=(sale_type == 'walk_in'),
        )
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)

    # Replay de idempotencia: incluir la clave para trazabilidad.
    if not created:
        return jsonify(success=True, data=_sale_dict(sale, with_wa_link=True),
                       replay=True)
    return jsonify(success=True, data=_sale_dict(sale, with_wa_link=True)), 201


@sales_bp.route('/businesses/<int:business_id>/sales', methods=['GET'])
def get_sales(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err

    try:
        sales = list_sales(
            biz.id,
            status=request.args.get('status'),
            date_from=request.args.get('date_from', type=str),
            date_to=request.args.get('date_to', type=str),
        )
    except VerdurasValidationError as e:
        return _error_response(e)
    return jsonify(success=True,
                   data={'sales': [_sale_dict(s) for s in sales]})


@sales_bp.route('/businesses/<int:business_id>/sales/<int:sale_id>', methods=['GET'])
def get_sale_detail(business_id: int, sale_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    sale = get_sale(biz.id, sale_id)
    if sale is None:
        return jsonify(success=False, error_code='not_found'), 404
    return jsonify(success=True, data=_sale_dict(sale, with_wa_link=True))


@sales_bp.route('/businesses/<int:business_id>/sales/<int:sale_id>/complete',
                methods=['POST'])
def post_complete(business_id: int, sale_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        sale = mark_completed(biz.id, sale_id)
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_sale_dict(sale))


@sales_bp.route('/businesses/<int:business_id>/sales/<int:sale_id>/cancel',
                methods=['POST'])
def post_cancel(business_id: int, sale_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    err = _api_key_or_error()
    if err:
        return err
    try:
        sale = mark_cancelled(biz.id, sale_id)
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_sale_dict(sale))

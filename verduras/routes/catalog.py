"""
API JSON del catálogo Verduras (Semana 1).

Las rutas solo orquestan: parsean request, llaman a
verduras/services/catalog.py y devuelven respuesta. Toda la validación y
lógica vive en el servicio (convención del repo).

Auth:
- Lecturas (GET): públicas por ahora (menú público futuro).
- Mutaciones (POST): header `x-api-key` contra SERVICE_API_KEY, mismo
  patrón server-to-server que core.

Scoping: TODOS los endpoints exigen `business_id` explícito; el servicio
valida que el recurso pertenezca a ese business (anti-IDOR). El guard de
vertical ('verduras') se aplica igual que en businesses.py.
"""
from flask import Blueprint, jsonify, request

from ..auth import VerdurasAuthError, require_service_api_key
from ..services.catalog import (
    VerdurasNotFoundError,
    VerdurasValidationError,
    create_category,
    create_product,
    get_product,
    list_categories,
    list_products,
    update_price,
)
from ..services.context import (
    BusinessNotFoundError,
    BusinessNotVegetalError,
    require_business,
)

catalog_bp = Blueprint('catalog', __name__, url_prefix='/api/verduras')


def _business_or_error(business_id):
    """Resuelve y valida el Business del vertical; devuelve (biz, None) o (None, response)."""
    try:
        return require_business(business_id), None
    except BusinessNotFoundError:
        return None, (jsonify(success=False, error_code='business_not_found'), 404)
    except BusinessNotVegetalError as e:
        return None, (jsonify(success=False, error_code='business_not_available', message=str(e)), 409)


def _category_dict(cat) -> dict:
    return {'id': cat.id, 'name': cat.name, 'is_active': cat.is_active}


def _product_dict(p, with_history: bool = False) -> dict:
    data = {
        'id': p.id,
        'category_id': p.category_id,
        'name': p.name,
        'unit': p.unit,
        'current_price': str(p.current_price),
        'photo_url': p.photo_url,
        'is_active': p.is_active,
    }
    if with_history:
        data['price_history'] = [
            {
                'price': str(h.price),
                'effective_from': h.effective_from.isoformat() if h.effective_from else None,
                'source': h.source,
                'note': h.note,
            }
            for h in p.price_history
        ]
    return data


def _error_response(e: Exception):
    if isinstance(e, VerdurasNotFoundError):
        return jsonify(success=False, error_code='not_found', message=str(e)), 404
    return jsonify(success=False, error_code='validation_error', message=str(e)), 400


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ── Categorías ──────────────────────────────────────────────


@catalog_bp.route('/businesses/<int:business_id>/categories', methods=['GET'])
def get_categories(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    cats = list_categories(biz.id, include_inactive=request.args.get('include_inactive') == 'true')
    return jsonify(success=True, data={'categories': [_category_dict(c) for c in cats]})


@catalog_bp.route('/businesses/<int:business_id>/categories', methods=['POST'])
def post_category(business_id: int):
    try:
        require_service_api_key()
    except VerdurasAuthError as e:
        return jsonify(success=False, error_code='unauthorized', message=str(e)), 401

    biz, err = _business_or_error(business_id)
    if err:
        return err
    try:
        cat = create_category(biz.id, _body().get('name'))
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_category_dict(cat)), 201


# ── Productos ───────────────────────────────────────────────


@catalog_bp.route('/businesses/<int:business_id>/products', methods=['GET'])
def get_products(business_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    category_id = request.args.get('category_id', type=int)
    include_inactive = request.args.get('include_inactive') == 'true'
    products = list_products(biz.id, category_id=category_id, include_inactive=include_inactive)
    return jsonify(success=True, data={'products': [_product_dict(p) for p in products]})


@catalog_bp.route('/businesses/<int:business_id>/products', methods=['POST'])
def post_product(business_id: int):
    try:
        require_service_api_key()
    except VerdurasAuthError as e:
        return jsonify(success=False, error_code='unauthorized', message=str(e)), 401

    biz, err = _business_or_error(business_id)
    if err:
        return err
    body = _body()
    try:
        product = create_product(
            biz.id,
            category_id=body.get('category_id'),
            name=body.get('name'),
            unit=body.get('unit'),
            price=body.get('price'),
            photo_url=body.get('photo_url'),
        )
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_product_dict(product)), 201


@catalog_bp.route('/businesses/<int:business_id>/products/<int:product_id>', methods=['GET'])
def get_product_detail(business_id: int, product_id: int):
    biz, err = _business_or_error(business_id)
    if err:
        return err
    product = get_product(biz.id, product_id)
    if product is None:
        return jsonify(success=False, error_code='not_found'), 404
    return jsonify(success=True, data=_product_dict(product, with_history=True))


@catalog_bp.route('/businesses/<int:business_id>/products/<int:product_id>/price', methods=['POST'])
def post_price(business_id: int, product_id: int):
    """Cambio de precio diario: actualiza current_price y appendea historial."""
    try:
        require_service_api_key()
    except VerdurasAuthError as e:
        return jsonify(success=False, error_code='unauthorized', message=str(e)), 401

    biz, err = _business_or_error(business_id)
    if err:
        return err
    body = _body()
    try:
        product = update_price(
            biz.id, product_id,
            new_price=body.get('price'),
            source=body.get('source') or 'manual',
            note=body.get('note'),
        )
    except (VerdurasValidationError, VerdurasNotFoundError) as e:
        return _error_response(e)
    return jsonify(success=True, data=_product_dict(product, with_history=True))

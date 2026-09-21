"""
API JSON de Businesses para el vertical Verduras.

Lee `businesses` (tabla del puente en core) filtrando por el vertical.
Solo endpoints de lectura: el alta/edición de Businesses de este vertical
irá por un dashboard propio en fases siguientes.
"""
from flask import Blueprint, jsonify

from ..services.context import list_verduras_businesses

businesses_bp = Blueprint('businesses', __name__, url_prefix='/api/businesses')


def _serialize(biz) -> dict:
    return {
        'id': biz.id,
        'name': biz.name,
        'slug': biz.slug,
        'vertical': biz.vertical,
        'is_active': biz.is_active,
        'created_at': biz.created_at.isoformat() if biz.created_at else None,
    }


@businesses_bp.route('', methods=['GET'])
def list_businesses():
    bizs = list_verduras_businesses()
    return jsonify(success=True, data={'businesses': [_serialize(b) for b in bizs]})


@businesses_bp.route('/<int:business_id>', methods=['GET'])
def get_business_detail(business_id: int):
    from ..services.context import (
        BusinessNotFoundError,
        BusinessNotVegetalError,
        require_business,
    )

    try:
        biz = require_business(business_id)
    except BusinessNotFoundError:
        return jsonify(success=False, error_code='business_not_found'), 404
    except BusinessNotVegetalError as e:
        return jsonify(success=False, error_code='business_not_available', message=str(e)), 409
    return jsonify(success=True, data=_serialize(biz))

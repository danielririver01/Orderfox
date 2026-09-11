import uuid

from flask import Blueprint, jsonify, request

from app.services.table_service import TableService
from app.utils.auth import require_active, require_auth, require_feature
from app.utils.jwt_auth import get_current_restaurant_jwt

api_tables_bp = Blueprint('api_tables', __name__, url_prefix='/api/tables')

@api_tables_bp.route('', methods=['GET'])
@require_auth
@require_active
def list_tables():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    tables = TableService.get_tables(restaurant.id)

    return jsonify({
        'success': True,
        'data': {
            'tables': [
                {
                    'id': t.id,
                    'name': t.name,
                    'capacity': t.capacity,
                    'qr_code': t.qr_code,
                    'is_active': t.is_active,
                    'active_orders_count': TableService.get_active_orders_count(restaurant.id, t.id)
                }
                for t in tables
            ]
        }
    })

@api_tables_bp.route('', methods=['POST'])
@require_auth
@require_active
@require_feature('has_table_qr')
def create_table():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Nombre es requerido'}), 400

    capacity = data.get('capacity')  # opcional (reservas v1.5)
    qr_code = f"table-{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}"

    table, error = TableService.create_table(restaurant.id, name, qr_code=qr_code, capacity=capacity)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': table.id,
            'name': table.name,
            'capacity': table.capacity,
            'qr_code': table.qr_code,
            'is_active': table.is_active
        }
    }), 201

@api_tables_bp.route('/<int:id>/capacity', methods=['PATCH'])
@require_auth
@require_active
def update_capacity(id):
    """Capacidad de la mesa (reservas v1.5). Sin @require_feature: la
    capacidad es editable por cualquier plan activo (los datos alimentan
    reservas futuras y la configuración no se pierde si cambian de plan)."""
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json(silent=True) or {}
    table, error = TableService.update_capacity(restaurant.id, id, data.get('capacity'))
    if error:
        status = 404 if error == 'Mesa no encontrada' else 400
        return jsonify({'success': False, 'error': error}), status

    return jsonify({
        'success': True,
        'data': {'id': table.id, 'name': table.name, 'capacity': table.capacity}
    })

@api_tables_bp.route('/<int:id>', methods=['DELETE'])
@require_auth
@require_active
@require_feature('has_table_qr')
def delete_table(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    table = TableService.get_table(restaurant.id, id)
    if not table:
        return jsonify({'success': False, 'error': 'Mesa no encontrada'}), 404

    success, error = TableService.delete_table(table, check_active_orders=True)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': 'Mesa eliminada exitosamente'})

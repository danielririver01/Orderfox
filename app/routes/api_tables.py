from flask import Blueprint, jsonify, request
from app.utils.auth import require_auth, require_active, require_feature
from app.utils.jwt_auth import get_current_restaurant_jwt
from app.services.table_service import TableService
import uuid

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

    qr_code = f"table-{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}"

    table, error = TableService.create_table(restaurant.id, name, qr_code=qr_code)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': table.id,
            'name': table.name,
            'qr_code': table.qr_code,
            'is_active': table.is_active
        }
    }), 201

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

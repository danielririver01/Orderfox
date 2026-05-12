from flask import Blueprint, jsonify, request
from app import db
from app.models import Table, Order
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, jwt_feature_required, get_current_restaurant_jwt

api_tables_bp = Blueprint('api_tables', __name__, url_prefix='/api/tables')


@api_tables_bp.route('', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_tables():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    tables = Table.query.filter_by(restaurant_id=restaurant.id).all()

    return jsonify({
        'success': True,
        'data': {
            'tables': [
                {
                    'id': t.id,
                    'name': t.name,
                    'qr_code': t.qr_code,
                    'is_active': t.is_active,
                    'active_orders_count': Order.query.filter_by(
                        table_id=t.id,
                        restaurant_id=restaurant.id,
                        status='pending'
                    ).count()
                }
                for t in tables
            ]
        }
    })


@api_tables_bp.route('', methods=['POST'])
@jwt_login_required
@jwt_active_required
@jwt_feature_required('has_table_qr')
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

    import uuid
    qr_code = f"table-{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}"

    table = Table(
        restaurant_id=restaurant.id,
        name=name,
        qr_code=qr_code,
        is_active=True
    )

    db.session.add(table)
    db.session.commit()

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
@jwt_login_required
@jwt_active_required
@jwt_feature_required('has_table_qr')
def delete_table(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    table = Table.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not table:
        return jsonify({'success': False, 'error': 'Mesa no encontrada'}), 404

    active_orders = Order.query.filter_by(
        table_id=id,
        restaurant_id=restaurant.id,
        status='pending'
    ).count()

    if active_orders > 0:
        return jsonify({
            'success': False,
            'error': f'No se puede eliminar porque tiene {active_orders} orden(es) activa(s)'
        }), 400

    db.session.delete(table)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Mesa eliminada exitosamente'})

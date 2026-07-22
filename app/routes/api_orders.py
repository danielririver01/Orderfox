from flask import Blueprint, jsonify, request
from app import db
from app.models import Order
from app.utils.auth import require_auth, require_active, require_feature
from app.utils.jwt_auth import get_current_restaurant_jwt
from app.utils.subscription import check_feature_access
from app.services.order_service import OrderService
from app.services.notification_service import notify_new_order

api_orders_bp = Blueprint('api_orders', __name__, url_prefix='/api/orders')


@api_orders_bp.route('', methods=['GET'])
@require_auth
@require_active
def list_orders():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    status_filter = request.args.get('status')
    sort_order = request.args.get('sort', 'desc')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Obtener queries base del servicio
    active_query = OrderService.get_active_orders_query(restaurant.id)
    completed_query = OrderService.get_today_completed_orders_query(restaurant.id)

    # Aplicar filtro de status si existe
    if status_filter:
        if status_filter in ['pending', 'confirmed']:
            completed_query = completed_query.filter(Order.status == status_filter)
            if status_filter == 'pending':
                query = active_query.filter(Order.status == 'pending')
            else:
                query = active_query.filter(Order.status == 'confirmed')
        else:
            active_query = active_query.filter(Order.status == status_filter)
            query = completed_query

        if sort_order == 'desc':
            query = query.order_by(Order.created_at.desc())
        else:
            query = query.order_by(Order.created_at.asc())

        total = query.count()
        orders = query.offset((page - 1) * per_page).limit(per_page).all()
    else:
        # Combinar ambas consultas con el servicio
        all_orders = OrderService.get_combined_orders(restaurant.id, sort_order)

        total = len(all_orders)
        start = (page - 1) * per_page
        orders = all_orders[start:start + per_page]

    return jsonify({
        'success': True,
        'data': {
            'orders': [OrderService.serialize_order(o) for o in orders],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
            }
        }
    })


@api_orders_bp.route('/<int:id>', methods=['GET'])
@require_auth
@require_active
def get_order(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    return jsonify({
        'success': True,
        'data': {
            'id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'status': order.status,
            'total': order.total,
            'notes': order.notes,
            'table': {
                'id': order.table_id,
                'name': order.table.name if order.table else None
            } if order.table_id else None,
            'items': [
                {
                    'id': item.id,
                    'product_name': item.product_name,
                    'product_price': item.product_price,
                    'quantity': item.quantity,
                    'modifiers_snapshot': item.modifiers_snapshot,
                    'subtotal': item.subtotal
                }
                for item in order.items
            ],
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None
        }
    })


@api_orders_bp.route('', methods=['POST'])
@require_auth
@require_active
def create_order():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    table_id = data.get('table_id')
    items_data = data.get('items', [])

    if not items_data:
        return jsonify({'success': False, 'error': 'Al menos un producto es requerido'}), 400

    if table_id:
        table = OrderService.validate_table(restaurant.id, table_id)
        if not table:
            return jsonify({'success': False, 'error': 'Mesa no encontrada'}), 404

    order_data = {
        'customer_name': data.get('customer_name', 'Cliente'),
        'customer_phone': data.get('customer_phone', ''),
        'notes': data.get('notes', ''),
        'table_id': table_id,
        'pending_expiry_hours': restaurant.pending_expiry_hours or 24,
    }

    order = OrderService.create_order(restaurant.id, order_data)
    try:
        total, _ = OrderService.add_items_to_order(order, items_data, restaurant.id)
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    db.session.commit()

    order_id = order.id
    notify_new_order(order_id)

    return jsonify({
        'success': True,
        'data': {
            'id': order_id,
            'order_number': order.order_number,
            'total': total,
            'status': order.status
        }
    }), 201


@api_orders_bp.route('/<int:id>/status', methods=['PATCH'])
@require_auth
@require_active
def change_status(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'success': False, 'error': 'Status es requerido'}), 400

    new_status = data.get('status')

    if not check_feature_access(restaurant, 'has_status_management') and new_status not in ['confirmed', 'cancelled', 'pending']:
        return jsonify({
            'success': False,
            'error': f'Tu plan {restaurant.plan_type.capitalize()} no permite marcar pedidos como Entregados.'
        }), 403

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    if not OrderService.validate_status_transition(order.status, new_status):
        return jsonify({
            'success': False,
            'error': f'No se puede cambiar de {order.status} a {new_status}'
        }), 400

    OrderService.change_order_status(order, new_status)

    return jsonify({
        'success': True,
        'data': {
            'id': order.id,
            'status': order.status,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None
        }
    })


@api_orders_bp.route('/<int:id>/cancel', methods=['POST'])
@require_auth
@require_active
def cancel_order(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    success, error = OrderService.cancel_order(order)
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400

    return jsonify({
        'success': True,
        'data': {
            'id': order.id,
            'status': order.status
        }
    })


@api_orders_bp.route('/<int:id>/receipt', methods=['GET'])
@require_auth
@require_active
def get_receipt(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    return jsonify({
        'success': True,
        'data': {
            'order_number': order.order_number,
            'restaurant_name': restaurant.name,
            'customer_name': order.customer_name,
            'status': order.status,
            'notes': order.notes,
            'items': [
                {
                    'product_name': item.product_name,
                    'quantity': item.quantity,
                    'price': item.product_price,
                    'modifiers': item.modifiers_snapshot,
                    'subtotal': item.subtotal
                }
                for item in order.items
            ],
            'total': order.total,
            'created_at': order.created_at.isoformat() if order.created_at else None
        }
    })


@api_orders_bp.route('/<int:id>', methods=['DELETE'])
@require_auth
@require_active
def delete_order(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    success, error = OrderService.delete_order(order)
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400

    return jsonify({'success': True, 'message': 'Orden eliminada exitosamente'})

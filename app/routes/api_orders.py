from flask import Blueprint, jsonify, request
from app import db
from app.models import Order, OrderItem, Product, Table, Modifier
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, jwt_feature_required, get_current_restaurant_jwt
from app.utils.subscription import check_feature_access
from datetime import date, datetime
import json

api_orders_bp = Blueprint('api_orders', __name__, url_prefix='/api/orders')


def generate_order_number(restaurant_id):
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    count = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.created_at >= today_start
    ).count()
    return f"ORD-{count + 1:03d}"


def validate_status_transition(current_status, new_status):
    valid_transitions = {
        'pending': ['confirmed', 'cancelled', 'expired'],
        'confirmed': ['delivered', 'cancelled'],
        'delivered': [],
        'cancelled': ['pending'],
        'expired': []
    }
    return new_status in valid_transitions.get(current_status, [])


@api_orders_bp.route('', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_orders():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    status_filter = request.args.get('status')
    sort_order = request.args.get('sort', 'desc')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    query = Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start
    )

    if status_filter:
        query = query.filter_by(status=status_filter)

    total = query.count()

    if sort_order == 'desc':
        query = query.order_by(Order.created_at.desc())
    else:
        query = query.order_by(Order.created_at.asc())

    orders = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'success': True,
        'data': {
            'orders': [
                {
                    'id': o.id,
                    'order_number': o.order_number,
                    'customer_name': o.customer_name,
                    'customer_phone': o.customer_phone,
                    'status': o.status,
                    'total': o.total,
                    'notes': o.notes,
                    'table_name': o.table.name if o.table else None,
                    'items_count': len(o.items),
                    'created_at': o.created_at.isoformat() if o.created_at else None
                }
                for o in orders
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
            }
        }
    })


@api_orders_bp.route('/<int:id>', methods=['GET'])
@jwt_login_required
@jwt_active_required
def get_order(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first()
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
@jwt_login_required
@jwt_active_required
def create_order():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    customer_name = data.get('customer_name', 'Cliente')
    customer_phone = data.get('customer_phone', '')
    table_id = data.get('table_id')
    notes = data.get('notes', '')
    items_data = data.get('items', [])

    if not items_data:
        return jsonify({'success': False, 'error': 'Al menos un producto es requerido'}), 400

    if table_id:
        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).first()
        if not table:
            return jsonify({'success': False, 'error': 'Mesa no encontrada'}), 404

    order_number = generate_order_number(restaurant.id)

    order = Order(
        restaurant_id=restaurant.id,
        order_number=order_number,
        customer_name=customer_name,
        customer_phone=customer_phone,
        notes=notes,
        total=0,
        status='pending',
        table_id=table_id
    )
    db.session.add(order)
    db.session.flush()

    total = 0

    for item_data in items_data:
        product = Product.query.filter_by(
            id=item_data.get('product_id'),
            restaurant_id=restaurant.id,
            is_active=True
        ).first()
        if not product:
            continue

        quantity = item_data.get('quantity', 1)
        modifiers_snapshot = None
        extras_price = 0

        modifier_ids = item_data.get('modifier_ids', [])
        if modifier_ids:
            modifiers = Modifier.query.filter(
                Modifier.id.in_(modifier_ids),
                Modifier.product_id == product.id,
                Modifier.is_active == True
            ).all()
            if modifiers:
                modifiers_snapshot = json.dumps([
                    {'name': m.name, 'price': m.extra_price} for m in modifiers
                ])
                extras_price = sum(m.extra_price for m in modifiers)

        subtotal = (product.price + extras_price) * quantity

        order_item = OrderItem(
            order_id=order.id,
            restaurant_id=restaurant.id,
            product_name=product.name,
            product_price=product.price,
            quantity=quantity,
            modifiers_snapshot=modifiers_snapshot,
            subtotal=subtotal
        )
        db.session.add(order_item)
        total += subtotal

    order.total = total
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': order.id,
            'order_number': order.order_number,
            'total': total,
            'status': order.status
        }
    }), 201


@api_orders_bp.route('/<int:id>/status', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
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

    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    if not validate_status_transition(order.status, new_status):
        return jsonify({
            'success': False,
            'error': f'No se puede cambiar de {order.status} a {new_status}'
        }), 400

    order.status = new_status
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': order.id,
            'status': order.status,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None
        }
    })


@api_orders_bp.route('/<int:id>/cancel', methods=['POST'])
@jwt_login_required
@jwt_active_required
def cancel_order(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    if order.status in ['delivered', 'cancelled']:
        return jsonify({
            'success': False,
            'error': 'No se puede cancelar un pedido entregado o ya cancelado'
        }), 400

    order.status = 'cancelled'
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': order.id,
            'status': order.status
        }
    })


@api_orders_bp.route('/<int:id>/receipt', methods=['GET'])
@jwt_login_required
@jwt_active_required
def get_receipt(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first()
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
@jwt_login_required
@jwt_active_required
def delete_order(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not order:
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404

    if order.status != 'cancelled':
        return jsonify({
            'success': False,
            'error': 'Solo se pueden eliminar órdenes canceladas'
        }), 400

    db.session.delete(order)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Orden eliminada exitosamente'})

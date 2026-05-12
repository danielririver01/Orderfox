from flask import Blueprint, jsonify, request, current_app
from app import db
from app.models import Order, Restaurant, User, Product
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, jwt_feature_required, get_current_restaurant_jwt, get_current_user_jwt
from app.utils.subscription import get_plan_limits, AI_TOKEN_LIMITS, get_subscription_status, check_feature_access
from datetime import date, datetime, timezone
from sqlalchemy import func
import jwt as pyjwt
from datetime import timedelta

api_dashboard_bp = Blueprint('api_dashboard', __name__, url_prefix='/api/dashboard')


@api_dashboard_bp.route('/overview')
@jwt_login_required
@jwt_active_required
def overview():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    menu_url = f"{current_app.config.get('BASE_URL', 'https://velzia.co')}/menu/{restaurant.slug}"
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    stats = db.session.query(
        Order.status,
        func.count(Order.id)
    ).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start
    ).group_by(Order.status).all()
    counts = {s: c for s, c in stats}

    total_sales = db.session.query(func.sum(Order.total)).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start,
        Order.status.in_(['confirmed', 'delivered'])
    ).scalar() or 0

    return jsonify({
        'success': True,
        'data': {
            'restaurant': {
                'name': restaurant.name,
                'slug': restaurant.slug,
                'is_open': restaurant.is_open,
                'plan_type': restaurant.plan_type
            },
            'stats': {
                'today_orders': sum(counts.values()),
                'pending': counts.get('pending', 0),
                'confirmed': counts.get('confirmed', 0),
                'preparing': counts.get('preparing', 0),
                'delivered': counts.get('delivered', 0),
                'cancelled': counts.get('cancelled', 0),
                'today_sales_cop': int(total_sales),
            },
            'menu_url': menu_url
        }
    })


@api_dashboard_bp.route('/toggle-status', methods=['POST'])
@jwt_login_required
@jwt_active_required
@jwt_feature_required('has_status_management')
def toggle_status():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data or 'is_open' not in data:
        return jsonify({'success': False, 'error': 'is_open es requerido'}), 400

    restaurant.is_open = data.get('is_open')
    db.session.commit()

    return jsonify({'success': True, 'data': {'is_open': restaurant.is_open}})


@api_dashboard_bp.route('/check-orders')
@jwt_login_required
@jwt_active_required
def check_orders():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    base_filter = (
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start
    )

    last_id = db.session.query(func.max(Order.id)).filter(*base_filter).scalar() or 0

    pending_count = Order.query.filter(
        *base_filter,
        Order.status == 'pending'
    ).count()

    new_orders = Order.query.filter(
        *base_filter,
        Order.status == 'pending'
    ).order_by(Order.created_at.desc()).limit(10).all()

    return jsonify({
        'success': True,
        'data': {
            'last_id': last_id,
            'pending_count': pending_count,
            'new_orders': [
                {
                    'id': o.id,
                    'order_number': o.order_number,
                    'customer_name': o.customer_name,
                    'total': o.total,
                    'status': o.status,
                    'created_at': o.created_at.isoformat() if o.created_at else None
                }
                for o in new_orders
            ]
        }
    })


@api_dashboard_bp.route('/stats')
@jwt_login_required
@jwt_active_required
def stats():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    range_type = request.args.get('range', 'today')
    today = date.today()

    if range_type == 'month':
        start_date = datetime.combine(today.replace(day=1), datetime.min.time())
    elif range_type == 'week':
        start_date = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    else:
        start_date = datetime.combine(today, datetime.min.time())

    total_sales = db.session.query(func.sum(Order.total)).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= start_date,
        Order.status.in_(['confirmed', 'delivered'])
    ).scalar() or 0

    total_orders = Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= start_date
    ).count()

    orders_by_status = db.session.query(
        Order.status,
        func.count(Order.id)
    ).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= start_date
    ).group_by(Order.status).all()

    status_counts = {s: c for s, c in orders_by_status}

    avg_order_value = int(total_sales) / total_orders if total_orders > 0 else 0

    return jsonify({
        'success': True,
        'data': {
            'total_orders': total_orders,
            'total_sales_cop': int(total_sales),
            'avg_order_value_cop': int(avg_order_value),
            'orders_by_status': status_counts,
            'range': range_type
        }
    })


@api_dashboard_bp.route('/settings')
@jwt_login_required
@jwt_active_required
def settings():
    user = get_current_user_jwt()
    restaurant = get_current_restaurant_jwt()

    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    sub_status = get_subscription_status(restaurant)

    return jsonify({
        'success': True,
        'data': {
            'restaurant': {
                'id': restaurant.id,
                'name': restaurant.name,
                'slug': restaurant.slug,
                'whatsapp_phone': restaurant.whatsapp_phone,
                'plan_type': restaurant.plan_type,
                'subscription_expires_at': restaurant.subscription_expires_at.isoformat() if restaurant.subscription_expires_at else None,
                'is_active': restaurant.is_active,
                'is_open': restaurant.is_open,
                'created_at': restaurant.created_at.isoformat() if restaurant.created_at else None
            },
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            },
            'subscription': sub_status
        }
    })


@api_dashboard_bp.route('/subscription')
@jwt_login_required
@jwt_active_required
def subscription():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    user = get_current_user_jwt()
    sub_status = get_subscription_status(restaurant)
    plan_info = get_plan_limits(restaurant.plan_type)
    plan_info['ai_tokens'] = AI_TOKEN_LIMITS.get(restaurant.plan_type, 0)

    products_used = Product_count = Product.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).count()

    ai_tokens_used = 0
    ai_tokens_limit = plan_info.get('ai_tokens', 0)
    if user.token_wallet:
        ai_tokens_used = user.token_wallet.tokens_used_month

    return jsonify({
        'success': True,
        'data': {
            'plan': {
                'type': restaurant.plan_type,
                'name': plan_info.get('name', restaurant.plan_type),
                'features': plan_info
            },
            'usage': {
                'products_used': products_used,
                'products_limit': plan_info.get('max_products', 25),
                'ai_tokens_used': ai_tokens_used,
                'ai_tokens_limit': ai_tokens_limit
            },
            'subscription': sub_status
        }
    })


@api_dashboard_bp.route('/profile', methods=['PUT'])
@jwt_login_required
@jwt_active_required
def update_profile():
    restaurant = get_current_restaurant_jwt()
    user = get_current_user_jwt()

    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    restaurant_name = data.get('restaurant_name')
    whatsapp_phone = data.get('whatsapp_phone')
    username = data.get('username')

    if restaurant_name:
        existing = Restaurant.query.filter(
            Restaurant.name == restaurant_name,
            Restaurant.id != restaurant.id
        ).first()
        if existing:
            return jsonify({'success': False, 'error': 'Este nombre ya está en uso'}), 400
        restaurant.name = restaurant_name

    if whatsapp_phone:
        restaurant.whatsapp_phone = whatsapp_phone

    if username:
        user.username = username.strip()

    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'restaurant': {
                'name': restaurant.name,
                'whatsapp_phone': restaurant.whatsapp_phone
            },
            'user': {
                'username': user.username
            }
        }
    })


@api_dashboard_bp.route('/change-password', methods=['POST'])
@jwt_login_required
def change_password():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    user = get_current_user_jwt()
    if not user:
        return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404

    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Contraseñas requeridas'}), 400

    if not user.check_password(current_password):
        return jsonify({'success': False, 'error': 'Contraseña actual incorrecta'}), 400

    if new_password != confirm_password:
        return jsonify({'success': False, 'error': 'Las nuevas contraseñas no coinciden'}), 400

    if len(new_password) < 8 or not any(c.isdigit() for c in new_password):
        return jsonify({
            'success': False,
            'error': 'La contraseña debe tener al menos 8 caracteres y un número'
        }), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Contraseña actualizada exitosamente'})


@api_dashboard_bp.route('/delete-account', methods=['POST'])
@jwt_login_required
def delete_account():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data or data.get('confirmation') != 'ELIMINAR':
        return jsonify({'success': False, 'error': 'Confirmación requerida: escribe ELIMINAR'}), 400

    try:
        db.session.delete(restaurant)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Cuenta eliminada permanentemente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Error al eliminar la cuenta'}), 500


@api_dashboard_bp.route('/ai-scan/token', methods=['POST'])
@jwt_login_required
@jwt_active_required
def ai_scan_token():
    user = get_current_user_jwt()
    if not user or not user.clerk_id:
        return jsonify({
            'success': False,
            'error': 'Necesitas una cuenta vinculada a Clerk para usar el Scanner IA.'
        }), 403

    scanner_url = current_app.config.get('SCANNER_IA_URL', 'http://localhost:3000')

    token_payload = {
        'clerk_id': user.clerk_id,
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=5),
        'iat': datetime.now(timezone.utc)
    }

    signed_token = pyjwt.encode(
        token_payload,
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )

    return jsonify({
        'success': True,
        'data': {
            'token': signed_token,
            'scanner_url': f'{scanner_url}/flask-auth?flask_token={signed_token}'
        }
    })

from flask import Blueprint, jsonify, request, current_app
from app import db
from app.models import Restaurant, User, Product
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, jwt_feature_required, get_current_restaurant_jwt, get_current_user_jwt
from app.utils.subscription import get_plan_limits, AI_TOKEN_LIMITS, get_subscription_status, check_feature_access
from datetime import datetime, timezone
import jwt as pyjwt
from datetime import timedelta
from app.services.dashboard_service import DashboardService

api_dashboard_bp = Blueprint('api_dashboard', __name__, url_prefix='/api/dashboard')


@api_dashboard_bp.route('/overview')
@jwt_login_required
@jwt_active_required
def overview():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    menu_url = f"{current_app.config.get('BASE_URL', 'https://velzia.co')}/menu/{restaurant.slug}"
    stats = DashboardService.get_today_overview(restaurant.id)

    return jsonify({
        'success': True,
        'data': {
            'restaurant': {
                'name': restaurant.name,
                'slug': restaurant.slug,
                'is_open': restaurant.is_open,
                'plan_type': restaurant.plan_type
            },
            'stats': stats,
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

    is_open = DashboardService.toggle_status(restaurant, data.get('is_open'))
    return jsonify({'success': True, 'data': {'is_open': is_open}})


@api_dashboard_bp.route('/check-orders')
@jwt_login_required
@jwt_active_required
def check_orders():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = DashboardService.get_order_polling(restaurant.id)
    return jsonify({'success': True, 'data': data})


@api_dashboard_bp.route('/stats')
@jwt_login_required
@jwt_active_required
def stats():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    range_type = request.args.get('range', 'today')
    data = DashboardService.get_extended_stats(restaurant.id, range_type)
    data['range'] = range_type
    return jsonify({'success': True, 'data': data})


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
            'scanner_url': f'{scanner_url}/flask-auth',
            'method': 'Authorization: Bearer <token>'
        }
    })

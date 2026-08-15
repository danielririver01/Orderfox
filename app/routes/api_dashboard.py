from flask import Blueprint, jsonify, request, current_app
from app.models import Restaurant, User
from app.utils.auth import require_auth, require_active, require_feature
from app.utils.jwt_auth import get_current_restaurant_jwt, get_current_user_jwt
from app.utils.subscription import get_plan_limits, AI_TOKEN_LIMITS, get_subscription_status
from datetime import datetime, timezone
import jwt as pyjwt
from datetime import timedelta
from app.services.dashboard_service import DashboardService
from app.services.product_service import ProductService

api_dashboard_bp = Blueprint('api_dashboard', __name__, url_prefix='/api/dashboard')


@api_dashboard_bp.route('/overview')
@require_auth
@require_active
def overview():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    menu_url = f"{current_app.config.get('ASTRO_BASE_URL') or current_app.config.get('BASE_URL', 'https://velzia.co')}/{restaurant.slug}/"
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
@require_auth
@require_active
@require_feature('has_status_management')
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
@require_auth
@require_active
def check_orders():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = DashboardService.get_order_polling(restaurant.id)
    return jsonify({'success': True, 'data': data})


@api_dashboard_bp.route('/stats')
@require_auth
@require_active
def stats():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    range_type = request.args.get('range', 'today')
    data = DashboardService.get_extended_stats(restaurant.id, range_type)
    data['range'] = range_type
    return jsonify({'success': True, 'data': data})


@api_dashboard_bp.route('/settings')
@require_auth
@require_active
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
@require_auth
@require_active
def subscription():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    user = get_current_user_jwt()
    sub_status = get_subscription_status(restaurant)
    plan_info = get_plan_limits(restaurant.plan_type)
    plan_info['ai_tokens'] = AI_TOKEN_LIMITS.get(restaurant.plan_type, 0)
    plan_info['ai_tokens_unlimited'] = False

    products_used = ProductService.get_active_count(restaurant.id)

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
@require_auth
@require_active
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

    if not restaurant_name or not whatsapp_phone or not username:
        return jsonify({'success': False, 'error': 'Todos los campos son obligatorios.'}), 400

    success, error = DashboardService.update_profile(restaurant, user, restaurant_name, whatsapp_phone, username)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

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
@require_auth
def delete_account():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    data = request.get_json()
    if not data or data.get('confirmation') != 'ELIMINAR':
        return jsonify({'success': False, 'error': 'Confirmación requerida: escribe ELIMINAR'}), 400

    success, result = DashboardService.delete_restaurant(
        restaurant,
        clerk_id=user.clerk_id if (user := get_current_user_jwt()) else None,
    )
    if success:
        return jsonify({'success': True, 'message': result['message']})
    else:
        return jsonify({'success': False, 'error': result['message']}), 500


@api_dashboard_bp.route('/ai-scan/token', methods=['POST'])
@require_auth
@require_active
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

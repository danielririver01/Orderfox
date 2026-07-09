from flask import Blueprint, jsonify, request, session as flask_session, current_app
from flask_jwt_extended import verify_jwt_in_request
from app.utils.auth import require_auth, require_active
from app.utils.jwt_auth import get_current_restaurant_jwt
from app.utils.restaurant import get_current_restaurant
from app.services.category_service import CategoryService

api_categories_bp = Blueprint('api_categories', __name__, url_prefix='/api/categories')

def _get_restaurant():
    try:
        verify_jwt_in_request()
        return get_current_restaurant_jwt()
    except Exception as e:
        current_app.logger.warning(f"JWT verification failed in _get_restaurant: {e}")
    if 'user_id' in flask_session:
        return get_current_restaurant()
    return None

@api_categories_bp.route('', methods=['GET'])
@require_auth
@require_active
def list_categories():
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    categories = CategoryService.get_categories(restaurant.id)
    return jsonify({
        'success': True,
        'data': {
            'categories': [
                {
                    'id': c.id,
                    'name': c.name,
                    'description': c.description,
                    'sort_order': c.sort_order,
                    'is_active': c.is_active,
                    'image_url': c.image_url,
                    'product_count': CategoryService.get_product_count(restaurant.id, c.id),
                    'created_at': c.created_at.isoformat() if c.created_at else None
                }
                for c in categories
            ]
        }
    })

@api_categories_bp.route('', methods=['POST'])
@require_auth
@require_active
def create_category():
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Nombre es requerido'}), 400
    category, error = CategoryService.create_category(
        restaurant_id=restaurant.id,
        name=name,
        description=request.form.get('description', '').strip(),
        is_active=request.form.get('is_active', 'true').lower() == 'true',
        image_file=request.files.get('image')
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({
        'success': True,
        'data': {
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'is_active': category.is_active,
            'image_url': category.image_url,
            'sort_order': category.sort_order
        }
    }), 201

@api_categories_bp.route('/<int:id>', methods=['GET'])
@require_auth
@require_active
def get_category(id):
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404
    return jsonify({
        'success': True,
        'data': {
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'sort_order': category.sort_order,
            'is_active': category.is_active,
            'image_url': category.image_url
        }
    })

@api_categories_bp.route('/<int:id>', methods=['PUT'])
@require_auth
@require_active
def update_category(id):
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404
    category, error = CategoryService.update_category(
        category=category,
        name=request.form.get('name'),
        description=request.form.get('description'),
        is_active=request.form.get('is_active').lower() == 'true' if request.form.get('is_active') is not None else None,
        image_file=request.files.get('image'),
        delete_image_flag=request.form.get('delete_image') == 'true'
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({
        'success': True,
        'data': {
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'is_active': category.is_active,
            'image_url': category.image_url
        }
    })

@api_categories_bp.route('/<int:id>', methods=['DELETE'])
@require_auth
@require_active
def delete_category(id):
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404
    success, error = CategoryService.delete_category(category)
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Categoría eliminada exitosamente'})

@api_categories_bp.route('/<int:id>/toggle', methods=['PATCH'])
@require_auth
@require_active
def toggle_category(id):
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404
    data = request.get_json()
    CategoryService.toggle_category(category, data.get('is_active'))
    return jsonify({'success': True, 'data': {'id': category.id, 'is_active': category.is_active}})

@api_categories_bp.route('/<int:id>/reorder', methods=['PATCH'])
@require_auth
@require_active
def reorder_category(id):
    restaurant = _get_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404
    data = request.get_json()
    success, error = CategoryService.reorder_category(category, data.get('sort_order'))
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'data': {'id': category.id, 'sort_order': category.sort_order}})

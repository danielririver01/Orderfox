from flask import Blueprint, jsonify, request
from app import db
from app.models import Category, Product
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, get_current_restaurant_jwt
from app.utils.image_handler import save_image, delete_image

api_categories_bp = Blueprint('api_categories', __name__, url_prefix='/api/categories')


@api_categories_bp.route('', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_categories():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    categories = Category.query.filter_by(
        restaurant_id=restaurant.id
    ).order_by(Category.sort_order).all()

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
                    'product_count': Product.query.filter_by(category_id=c.id, restaurant_id=restaurant.id).count(),
                    'created_at': c.created_at.isoformat() if c.created_at else None
                }
                for c in categories
            ]
        }
    })


@api_categories_bp.route('', methods=['POST'])
@jwt_login_required
@jwt_active_required
def create_category():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = request.form.get('is_active', 'true').lower() == 'true'

    if not name:
        return jsonify({'success': False, 'error': 'Nombre es requerido'}), 400

    max_order = db.session.query(db.func.max(Category.sort_order)).filter_by(
        restaurant_id=restaurant.id
    ).scalar() or 0

    category = Category(
        restaurant_id=restaurant.id,
        name=name,
        description=description,
        is_active=is_active,
        sort_order=max_order + 1
    )

    image_file = request.files.get('image')
    if image_file:
        image_url = save_image(image_file, 'categories')
        if image_url:
            category.image_url = image_url

    db.session.add(category)
    db.session.commit()

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
@jwt_login_required
@jwt_active_required
def get_category(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
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
@jwt_login_required
@jwt_active_required
def update_category(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404

    name = request.form.get('name')
    description = request.form.get('description')
    is_active = request.form.get('is_active')

    if name:
        category.name = name.strip()
    if description is not None:
        category.description = description.strip()
    if is_active is not None:
        category.is_active = is_active.lower() == 'true'

    image_file = request.files.get('image')
    if image_file:
        if category.image_url:
            delete_image(category.image_url)
        image_url = save_image(image_file, 'categories')
        if image_url:
            category.image_url = image_url
    elif request.form.get('delete_image') == 'true':
        if category.image_url:
            delete_image(category.image_url)
        category.image_url = None

    db.session.commit()

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
@jwt_login_required
@jwt_active_required
def delete_category(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404

    product_count = Product.query.filter_by(
        category_id=id,
        restaurant_id=restaurant.id
    ).count()

    if product_count > 0:
        return jsonify({
            'success': False,
            'error': f'No se puede eliminar porque tiene {product_count} producto(s) asociado(s)'
        }), 400

    if category.image_url:
        delete_image(category.image_url)

    db.session.delete(category)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Categoría eliminada exitosamente'})


@api_categories_bp.route('/<int:id>/toggle', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
def toggle_category(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404

    data = request.get_json()
    category.is_active = data.get('is_active', not category.is_active)
    db.session.commit()

    return jsonify({'success': True, 'data': {'id': category.id, 'is_active': category.is_active}})


@api_categories_bp.route('/<int:id>/reorder', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
def reorder_category(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404

    data = request.get_json()
    new_order = data.get('sort_order')

    if new_order is not None:
        category.sort_order = new_order
        db.session.commit()
        return jsonify({'success': True, 'data': {'id': category.id, 'sort_order': category.sort_order}})

    return jsonify({'success': False, 'error': 'sort_order requerido'}), 400

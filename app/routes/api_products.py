from flask import Blueprint, jsonify, request
from app.utils.jwt_auth import (
    jwt_login_required, jwt_active_required, jwt_feature_required,
    get_current_restaurant_jwt
)
from app.services.product_service import ProductService

api_products_bp = Blueprint('api_products', __name__, url_prefix='/api/products')


@api_products_bp.route('', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_products():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category_id = request.args.get('category_id', type=int)
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    products, total = ProductService.get_products_for_restaurant(
        restaurant.id,
        category_id=category_id,
        active_only=active_only,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'success': True,
        'data': {
            'products': [
                {
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'price': p.price,
                    'is_active': p.is_active,
                    'image_url': p.image_url,
                    'category_id': p.category_id,
                    'category_name': p.category.name if p.category else None,
                    'modifiers_count': ProductService.get_modifier_count(
                        restaurant.id, p.id
                    ),
                    'created_at': p.created_at.isoformat() if p.created_at else None,
                }
                for p in products
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 0,
            },
        }
    })


@api_products_bp.route('/<int:id>', methods=['GET'])
@jwt_login_required
@jwt_active_required
def get_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    modifiers = ProductService.get_modifiers_for_product(restaurant.id, id)

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': product.price,
            'is_active': product.is_active,
            'image_url': product.image_url,
            'category_id': product.category_id,
            'category_name': product.category.name if product.category else None,
            'modifiers': [
                {
                    'id': m.id,
                    'name': m.name,
                    'extra_price': m.extra_price,
                    'is_active': m.is_active,
                }
                for m in modifiers
            ],
        }
    })


@api_products_bp.route('', methods=['POST'])
@jwt_login_required
@jwt_active_required
def create_product():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    name = request.form.get('name', '').strip()
    price = request.form.get('price', type=int)
    category_id = request.form.get('category_id', type=int)

    if not name or not price or not category_id:
        return jsonify({
            'success': False,
            'error': 'Nombre, precio y categoría son requeridos'
        }), 400

    product, error = ProductService.create_product(
        restaurant_id=restaurant.id,
        category_id=category_id,
        name=name,
        price=price,
        description=request.form.get('description', '').strip(),
        is_active=request.form.get('is_active', 'true').lower() == 'true',
        image_file=request.files.get('image'),
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'category_id': product.category_id,
            'is_active': product.is_active,
            'image_url': product.image_url,
        }
    }), 201


@api_products_bp.route('/<int:id>', methods=['PUT'])
@jwt_login_required
@jwt_active_required
def update_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    # Parse form fields (partial update — None means skip)
    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price', type=int)
    category_id = request.form.get('category_id', type=int)
    is_active = request.form.get('is_active')

    # Convert is_active string to bool
    is_active_bool = None
    if is_active is not None:
        is_active_bool = is_active.lower() == 'true'

    image_file = request.files.get('image')
    delete_image_flag = request.form.get('delete_image') == 'true'

    product, error = ProductService.update_product(
        product=product,
        name=name.strip() if name else None,
        description=description.strip() if description is not None else None,
        price=price,
        category_id=category_id,
        is_active=is_active_bool,
        image_file=image_file,
        delete_image_flag=delete_image_flag,
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'is_active': product.is_active,
            'image_url': product.image_url,
        }
    })


@api_products_bp.route('/<int:id>', methods=['DELETE'])
@jwt_login_required
@jwt_active_required
def delete_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    ProductService.delete_product(product)

    return jsonify({
        'success': True,
        'message': 'Producto eliminado exitosamente'
    })


@api_products_bp.route('/<int:id>/toggle', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
def toggle_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    desired = data.get('is_active') if data else None

    product, error, limit_blocked = ProductService.toggle_product(
        product, desired
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'is_active': product.is_active,
        }
    })


# ── Modifier Endpoints ────────────────────────────────────────────────────


@api_products_bp.route('/<int:id>/modifiers', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_modifiers(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    modifiers = ProductService.get_modifiers_for_product(restaurant.id, id)

    return jsonify({
        'success': True,
        'data': {
            'modifiers': [
                {
                    'id': m.id,
                    'name': m.name,
                    'extra_price': m.extra_price,
                    'is_active': m.is_active,
                }
                for m in modifiers
            ]
        }
    })


@api_products_bp.route('/<int:id>/modifiers', methods=['POST'])
@jwt_login_required
@jwt_active_required
@jwt_feature_required('has_modifiers')
def create_modifier(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    name = data.get('name', '').strip()
    extra_price = data.get('extra_price', 0)

    if not name:
        return jsonify({'success': False, 'error': 'Nombre es requerido'}), 400

    modifier, error = ProductService.create_modifier(
        restaurant_id=restaurant.id,
        product_id=id,
        name=name,
        extra_price=extra_price,
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': modifier.id,
            'name': modifier.name,
            'extra_price': modifier.extra_price,
            'is_active': modifier.is_active,
        }
    }), 201


@api_products_bp.route('/modifiers/<int:id>/toggle', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
def toggle_modifier(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    modifier = ProductService.get_modifier(restaurant.id, id)
    if not modifier:
        return jsonify({'success': False, 'error': 'Modifier no encontrado'}), 404

    ProductService.toggle_modifier(modifier)

    return jsonify({
        'success': True,
        'data': {
            'id': modifier.id,
            'name': modifier.name,
            'extra_price': modifier.extra_price,
            'is_active': modifier.is_active,
        }
    })


@api_products_bp.route('/modifiers/<int:id>', methods=['DELETE'])
@jwt_login_required
@jwt_active_required
def delete_modifier(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    modifier = ProductService.get_modifier(restaurant.id, id)
    if not modifier:
        return jsonify({'success': False, 'error': 'Modifier no encontrado'}), 404

    ProductService.delete_modifier(modifier)

    return jsonify({
        'success': True,
        'message': 'Modifier eliminado exitosamente'
    })

from flask import Blueprint, jsonify, request
from app import db
from app.models import Product, Modifier, Category
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, jwt_feature_required, get_current_restaurant_jwt
from app.utils.subscription import check_product_limit
from app.utils.image_handler import save_image, delete_image

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

    query = Product.query.filter_by(restaurant_id=restaurant.id)

    if category_id:
        query = query.filter_by(category_id=category_id)
    if active_only:
        query = query.filter_by(is_active=True)

    query = query.order_by(Product.category_id, Product.name)

    total = query.count()
    products = query.offset((page - 1) * per_page).limit(per_page).all()

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
                    'is_highlighted': p.is_highlighted,
                    'image_url': p.image_url,
                    'category_id': p.category_id,
                    'category_name': p.category.name if p.category else None,
                    'modifiers_count': Modifier.query.filter_by(product_id=p.id, restaurant_id=restaurant.id).count(),
                    'created_at': p.created_at.isoformat() if p.created_at else None
                }
                for p in products
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
            }
        }
    })


@api_products_bp.route('/<int:id>', methods=['GET'])
@jwt_login_required
@jwt_active_required
def get_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    modifiers = Modifier.query.filter_by(product_id=id, restaurant_id=restaurant.id).all()

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': product.price,
            'is_active': product.is_active,
            'is_highlighted': product.is_highlighted,
            'image_url': product.image_url,
            'category_id': product.category_id,
            'category_name': product.category.name if product.category else None,
            'modifiers': [
                {
                    'id': m.id,
                    'name': m.name,
                    'extra_price': m.extra_price,
                    'is_active': m.is_active
                }
                for m in modifiers
            ]
        }
    })


@api_products_bp.route('', methods=['POST'])
@jwt_login_required
@jwt_active_required
def create_product():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    allowed, message = check_product_limit(restaurant)
    if not allowed:
        return jsonify({'success': False, 'error': message}), 400

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price = request.form.get('price', type=int)
    category_id = request.form.get('category_id', type=int)
    is_active = request.form.get('is_active', 'true').lower() == 'true'
    is_highlighted = request.form.get('is_highlighted', 'false').lower() == 'true'

    if not name or not price or not category_id:
        return jsonify({'success': False, 'error': 'Nombre, precio y categoría son requeridos'}), 400

    category = Category.query.filter_by(id=category_id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'success': False, 'error': 'Categoría inválida'}), 400

    product = Product(
        restaurant_id=restaurant.id,
        category_id=category_id,
        name=name,
        description=description,
        price=price,
        is_active=is_active,
        is_highlighted=is_highlighted
    )

    image_file = request.files.get('image')
    if image_file:
        image_url = save_image(image_file, 'products')
        if image_url:
            product.image_url = image_url

    db.session.add(product)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'category_id': product.category_id,
            'is_active': product.is_active,
            'is_highlighted': product.is_highlighted,
            'image_url': product.image_url
        }
    }), 201


@api_products_bp.route('/<int:id>', methods=['PUT'])
@jwt_login_required
@jwt_active_required
def update_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price', type=int)
    category_id = request.form.get('category_id', type=int)
    is_active = request.form.get('is_active')
    is_highlighted = request.form.get('is_highlighted')

    if name:
        product.name = name.strip()
    if description is not None:
        product.description = description.strip()
    if price is not None:
        product.price = price
    if category_id:
        category = Category.query.filter_by(id=category_id, restaurant_id=restaurant.id).first()
        if not category:
            return jsonify({'success': False, 'error': 'Categoría inválida'}), 400
        product.category_id = category_id
    if is_active is not None:
        desired = is_active.lower() == 'true'
        if desired and not product.is_active:
            allowed, message = check_product_limit(restaurant)
            if not allowed:
                return jsonify({'success': False, 'error': message}), 400
        product.is_active = desired
    if is_highlighted is not None:
        product.is_highlighted = is_highlighted.lower() == 'true'

    image_file = request.files.get('image')
    if image_file:
        if product.image_url:
            delete_image(product.image_url)
        image_url = save_image(image_file, 'products')
        if image_url:
            product.image_url = image_url
    elif request.form.get('delete_image') == 'true':
        if product.image_url:
            delete_image(product.image_url)
        product.image_url = None

    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'is_active': product.is_active,
            'is_highlighted': product.is_highlighted,
            'image_url': product.image_url
        }
    })


@api_products_bp.route('/<int:id>', methods=['DELETE'])
@jwt_login_required
@jwt_active_required
def delete_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    if product.image_url:
        delete_image(product.image_url)

    db.session.delete(product)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Producto eliminado exitosamente'})


@api_products_bp.route('/<int:id>/toggle', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
def toggle_product(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    desired = data.get('is_active')
    if desired is None:
        desired = not product.is_active

    if desired and not product.is_active:
        allowed, message = check_product_limit(restaurant)
        if not allowed:
            return jsonify({'success': False, 'error': message}), 400

    product.is_active = desired
    db.session.commit()

    return jsonify({'success': True, 'data': {'id': product.id, 'is_active': product.is_active}})


@api_products_bp.route('/<int:id>/modifiers', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_modifiers(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    modifiers = Modifier.query.filter_by(product_id=id, restaurant_id=restaurant.id).all()

    return jsonify({
        'success': True,
        'data': {
            'modifiers': [
                {
                    'id': m.id,
                    'name': m.name,
                    'extra_price': m.extra_price,
                    'is_active': m.is_active
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

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    name = data.get('name', '').strip()
    extra_price = data.get('extra_price', 0)

    if not name:
        return jsonify({'success': False, 'error': 'Nombre es requerido'}), 400

    modifier = Modifier(
        product_id=id,
        restaurant_id=restaurant.id,
        name=name,
        extra_price=extra_price,
        is_active=True
    )

    db.session.add(modifier)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': modifier.id,
            'name': modifier.name,
            'extra_price': modifier.extra_price,
            'is_active': modifier.is_active
        }
    }), 201


@api_products_bp.route('/modifiers/<int:id>/toggle', methods=['PATCH'])
@jwt_login_required
@jwt_active_required
def toggle_modifier(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    modifier = Modifier.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not modifier:
        return jsonify({'success': False, 'error': 'Modifier no encontrado'}), 404

    modifier.is_active = not modifier.is_active
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'id': modifier.id,
            'name': modifier.name,
            'extra_price': modifier.extra_price,
            'is_active': modifier.is_active
        }
    })


@api_products_bp.route('/modifiers/<int:id>', methods=['DELETE'])
@jwt_login_required
@jwt_active_required
def delete_modifier(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    modifier = Modifier.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not modifier:
        return jsonify({'success': False, 'error': 'Modifier no encontrado'}), 404

    product_id = modifier.product_id
    db.session.delete(modifier)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Modifier eliminado exitosamente'})

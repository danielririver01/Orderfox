from flask import Blueprint, jsonify, request
from app.models import Category, Product, Restaurant
from app.utils.subscription import is_subscription_active

api_public_bp = Blueprint('api_public', __name__, url_prefix='/api/public')


@api_public_bp.route('/menu/<string:slug>', methods=['GET'])
def get_menu(slug):
    restaurant = Restaurant.query.filter_by(slug=slug).first()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    if not restaurant.is_open:
        return jsonify({
            'success': False,
            'error': 'closed',
            'message': 'El restaurante está cerrado en este momento.'
        }), 403

    is_active_sub = restaurant.is_active and is_subscription_active(restaurant, include_grace_period=True)

    categories = Category.query.join(Product).filter(
        Category.restaurant_id == restaurant.id,
        Category.is_active == True,
        Product.is_active == True
    ).order_by(Category.sort_order).distinct().all()

    for cat in categories:
        cat.active_product_count = Product.query.filter_by(
            category_id=cat.id,
            restaurant_id=restaurant.id,
            is_active=True
        ).count()

    categories_data = []
    for cat in categories:
        products = Product.query.filter_by(
            category_id=cat.id,
            restaurant_id=restaurant.id,
            is_active=True
        ).all()

        products_data = []
        for p in products:
            modifiers = [
                {'id': m.id, 'name': m.name, 'extra_price': m.extra_price}
                for m in p.modifiers if m.is_active
            ]
            products_data.append({
                'id': p.id,
                'name': p.name,
                'description': p.description,
                'price': p.price,
                'image_url': p.image_url,
                'is_highlighted': p.is_highlighted,
                'modifiers': modifiers
            })

        categories_data.append({
            'id': cat.id,
            'name': cat.name,
            'image_url': cat.image_url,
            'product_count': cat.active_product_count,
            'products': products_data
        })

    highlighted = Product.query.filter_by(
        restaurant_id=restaurant.id,
        is_highlighted=True,
        is_active=True
    ).filter(Product.image_url.isnot(None)).all()

    if len(highlighted) < 3:
        ids_to_exclude = [p.id for p in highlighted]
        recent = Product.query.filter_by(
            restaurant_id=restaurant.id,
            is_active=True
        ).filter(
            Product.image_url.isnot(None),
            ~Product.id.in_(ids_to_exclude) if ids_to_exclude else True
        ).order_by(Product.created_at.desc()).limit(3 - len(highlighted)).all()
        highlighted.extend(recent)

    highlighted_data = [
        {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'image_url': p.image_url,
            'description': p.description
        }
        for p in highlighted[:3]
    ]

    return jsonify({
        'success': True,
        'data': {
            'restaurant': {
                'name': restaurant.name,
                'slug': restaurant.slug,
                'whatsapp_phone': restaurant.whatsapp_phone,
                'is_open': restaurant.is_open,
                'ordering_disabled': not is_active_sub
            },
            'categories': categories_data,
            'highlighted': highlighted_data
        }
    })


@api_public_bp.route('/menu/<string:slug>/categoria/<int:category_id>', methods=['GET'])
def get_category_products(slug, category_id):
    restaurant = Restaurant.query.filter_by(slug=slug).first()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(
        id=category_id,
        restaurant_id=restaurant.id
    ).first()
    if not category:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404

    products = Product.query.filter_by(
        category_id=category_id,
        restaurant_id=restaurant.id,
        is_active=True
    ).all()

    products_data = []
    for p in products:
        modifiers = [
            {'id': m.id, 'name': m.name, 'extra_price': m.extra_price}
            for m in p.modifiers if m.is_active
        ]
        products_data.append({
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': p.price,
            'image_url': p.image_url,
            'is_highlighted': p.is_highlighted,
            'modifiers': modifiers
        })

    return jsonify({
        'success': True,
        'data': {
            'category': {
                'id': category.id,
                'name': category.name,
                'description': category.description,
                'image_url': category.image_url
            },
            'products': products_data
        }
    })


@api_public_bp.route('/menu/<string:slug>/novedades', methods=['GET'])
def get_novedades(slug):
    restaurant = Restaurant.query.filter_by(slug=slug).first()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)

    query = Product.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).order_by(Product.created_at.desc())

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
                    'image_url': p.image_url,
                    'category_name': p.category.name if p.category else None,
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

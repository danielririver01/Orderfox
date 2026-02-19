from flask import Blueprint, render_template, abort, request, jsonify, redirect, url_for, session
from app.models import db, Category, Product, Order, OrderItem, Restaurant, Table
from datetime import datetime, date, timedelta
from app.utils.subscription import is_subscription_active, check_feature_access
import json

public_bp = Blueprint('public', __name__)

def generate_order_number(restaurant_id):
    count = Order.query.filter_by(restaurant_id=restaurant_id).count()
    return f"ORD-{count + 1:03d}"

@public_bp.route('/menu/<string:slug>')
@public_bp.route('/menu')
def menu(slug=None):
    # Si no hay slug, buscar el primero activo (MVP)
    if not slug:
        restaurant = Restaurant.query.first()
        if not restaurant:
            abort(404)
        return redirect(url_for('public.menu', slug=restaurant.slug, **request.args))
    
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()

    table_id = request.args.get('table')
    if table_id:
        has_table_qr_access = check_feature_access(restaurant, 'has_table_qr')

        if has_table_qr_access:
            table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).first()
            if table and table.is_active:
                session['table_id'] = table.id
                session['restaurant_id'] = restaurant.id # Por seguridad
            else:
                session.pop('table_id', None)
        else:
            session.pop('table_id', None)
    
    # Lógica de "Solo Lectura" para menú público
    # Si la suscripción expiró, SE MUESTRA EL MENÚ pero se desactivan los pedidos
    is_active_sub = restaurant.is_active and is_subscription_active(restaurant)
    ordering_disabled = not is_active_sub
    
    # Si está desactivado, forzamos store_open a False visualmente o lo manejamos con ordering_disabled
    store_open = restaurant.is_open and is_active_sub
    
    categories = Category.query.join(Product).filter(
        Category.restaurant_id == restaurant.id,
        Category.is_active == True,
        Product.is_active == True
    ).order_by(Category.sort_order).distinct().all()
    
    return render_template('public/menu_categories.html', 
                         categories=categories,
                         restaurant=restaurant,
                         store_open=store_open,
                         ordering_disabled=ordering_disabled)

@public_bp.route('/menu/<string:slug>/categoria/<int:category_id>')
def category_products(slug, category_id):
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    
    category = Category.query.filter_by(id=category_id, restaurant_id=restaurant.id).first_or_404()
    
    products = Product.query.filter_by(
        category_id=category_id,
        restaurant_id=restaurant.id,
        is_active=True
    ).all()
    
    # Lógica de "Solo Lectura"
    is_active_sub = restaurant.is_active and is_subscription_active(restaurant)
    ordering_disabled = not is_active_sub

    return render_template('public/menu_category_products.html',
                         restaurant=restaurant,
                         category=category,
                         products=products,
                         ordering_disabled=ordering_disabled)

@public_bp.route('/menu/api/order', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'cart' not in data:
        return jsonify({'success': False, 'error': 'Carrito vacío'}), 400

    restaurant = Restaurant.query.filter_by(id=data.get('restaurant_id', 1)).first()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    if not restaurant.is_open:
        return jsonify({
            'success': False, 
            'error': '⏰ Estamos cerrados en este momento. ¡Vuelve pronto!'
        }), 403
    
    # Validación estricta de suscripción (Backend)
    if not (restaurant.is_active and is_subscription_active(restaurant)):
        return jsonify({
            'success': False, 
            'error': 'Pedidos temporalmente desactivados.'
        }), 403

    expiration_limit = datetime.now() - timedelta(minutes=30)
    Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.status == 'pending',
        Order.created_at < expiration_limit
    ).update({Order.status: 'expired'})
    db.session.commit()

    client_ip = request.remote_addr
    rate_limit = datetime.now() - timedelta(seconds=90)
    recent_order = Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.notes.like(f"%IP:{client_ip}%"),
        Order.created_at > rate_limit
    ).first()

    if recent_order:
        return jsonify({
            'success': False, 
            'error': '¿Olvidaste algo? Espera unos segundos para enviar un nuevo pedido 🧃'
        }), 429

    order_number = generate_order_number(restaurant.id)
    
    order = Order(
        restaurant_id=restaurant.id,
        order_number=order_number,
        status='pending',
        total=data.get('total', 0),
        customer_name='Cliente Web',
        notes=f'Pedido realizado desde el menú digital.',
        table_id=session.get('table_id') if session.get('restaurant_id') == restaurant.id else None
    )
    db.session.add(order)
    db.session.flush()

    cart = data['cart']
    for product_id, item in cart.items():
        extras_total = sum(e['price'] for e in item.get('extras', []))
        subtotal = (item['price'] + extras_total) * item['quantity']

        order_item = OrderItem(
            order_id=order.id,
            restaurant_id=restaurant.id,
            product_name=item['name'],
            product_price=item['price'],
            quantity=item['quantity'],
            modifiers_snapshot=json.dumps(item.get('extras', [])),
            subtotal=subtotal
        )
        db.session.add(order_item)

    db.session.commit()
    
    return jsonify({
        'success': True, 
        'order_number': order_number,
        'order_id': order.id,
        'table_name': order.table.name if order.table else None
    })

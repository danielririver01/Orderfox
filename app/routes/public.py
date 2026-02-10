from flask import Blueprint, render_template, abort, request, jsonify, redirect, url_for
from app.models import db, Category, Product, Order, OrderItem, Restaurant
from datetime import datetime, date, timedelta
from app.utils.subscription import is_subscription_active
import json

public_bp = Blueprint('public', __name__)

def generate_order_number(restaurant_id):
    # ... (contenido existente omitido para brevedad)
    return f"ORD-{count + 1:03d}"

@public_bp.route('/menu/<string:slug>')
@public_bp.route('/menu')
def menu(slug=None):
    # Si no hay slug, buscar el primero activo (MVP)
    if not slug:
        restaurant = Restaurant.query.first()
        if not restaurant:
            abort(404)
        return redirect(url_for('public.menu', slug=restaurant.slug))
    
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    
    # VALIDACIÓN DE SEGURIDAD: Verificar si la cuenta está activa y la suscripción vigente
    if not (restaurant.is_active and is_subscription_active(restaurant)):
        return render_template('public/subscription_expired.html', restaurant=restaurant)
    
    # Notificar si la tienda está cerrada pero permitir ver el menú
    store_open = restaurant.is_open
    
    # Obtener solo categorías con productos activos
    categories = Category.query.join(Product).filter(
        Category.restaurant_id == restaurant.id,
        Category.is_active == True,
        Product.is_active == True
    ).order_by(Category.sort_order).distinct().all()
    
    return render_template('public/menu_categories.html', 
                         categories=categories,
                         restaurant=restaurant,
                         store_open=store_open)

@public_bp.route('/menu/<string:slug>/categoria/<int:category_id>')
def category_products(slug, category_id):
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    
    # VALIDACIÓN DE SEGURIDAD
    if not (restaurant.is_active and is_subscription_active(restaurant)):
        return render_template('public/subscription_expired.html', restaurant=restaurant)

    category = Category.query.filter_by(id=category_id, restaurant_id=restaurant.id).first_or_404()
    # ...
    
    # Solo productos activos de esta categoría
    products = Product.query.filter_by(
        category_id=category_id,
        restaurant_id=restaurant.id,
        is_active=True
    ).all()
    
    return render_template('public/menu_category_products.html',
                         restaurant=restaurant,
                         category=category,
                         products=products)

@public_bp.route('/menu/api/order', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'cart' not in data:
        return jsonify({'success': False, 'error': 'Carrito vacío'}), 400

    # Obtener el restaurante (por ahora el primero para el API simpler)
    # En el futuro, el frontend podría enviar el restaurant_id en el JSON
    restaurant = Restaurant.query.filter_by(id=data.get('restaurant_id', 1)).first()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    # 0. Validar si la tienda está abierta
    if not restaurant.is_open:
        return jsonify({
            'success': False, 
            'error': '⏰ Estamos cerrados en este momento. ¡Vuelve pronto!'
        }), 403
    
    # 0.1 Validar si la cuenta está activa (suspensión administrativa)
    if not restaurant.is_active:
        return jsonify({
            'success': False, 
            'error': '❌ Servicio temporalmente no disponible.'
        }), 403

    # 1. Limpieza Lazy: Expirar pedidos pendientes antiguos (>30 min)
    expiration_limit = datetime.now() - timedelta(minutes=30)
    Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.status == 'pending',
        Order.created_at < expiration_limit
    ).update({Order.status: 'expired'})
    db.session.commit()

    # 2. Anti-spam: Verificar último pedido de esta IP (<90 seg)
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
    
    # Crear la orden principal
    order = Order(
        restaurant_id=restaurant.id,
        order_number=order_number,
        status='pending',
        total=data.get('total', 0),
        customer_name='Cliente Web',
        notes=f'Pedido realizado desde el menú digital.'
    )
    db.session.add(order)
    db.session.flush()

    # Procesar items del carrito
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
        'order_id': order.id
    })

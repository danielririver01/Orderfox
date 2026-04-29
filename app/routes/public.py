from flask import Blueprint, render_template, abort, request, jsonify, redirect, url_for, session
from app.models import db, Category, Product, Order, OrderItem, Restaurant, Table, Modifier
from app import csrf
from datetime import datetime, date, timedelta, timezone
from app.utils.subscription import is_subscription_active, check_feature_access
from app.utils.rate_limiter import OrderRateLimiter
import json
import time

public_bp = Blueprint('public', __name__)

@public_bp.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@public_bp.route('/menu/api/init-checkout', methods=['POST'])
def init_checkout():
    """Registra el inicio del proceso de checkout en la sesión del usuario para anti-bots."""
    session['checkout_start_time'] = time.time()
    return jsonify({'success': True})

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
    
    # Bloqueo Radical: Si el local está cerrado por el dueño, mostramos la Landing de Cerrado
    if not restaurant.is_open:
        return render_template('public/store_closed.html', restaurant=restaurant)

    # Lógica de "Solo Lectura" por suscripción
    is_active_sub = restaurant.is_active and is_subscription_active(restaurant, include_grace_period=True)
    ordering_disabled = not is_active_sub
    
    categories = Category.query.join(Product).filter(
        Category.restaurant_id == restaurant.id,
        Category.is_active == True,
        Product.is_active == True
    ).order_by(Category.sort_order).distinct().all()

# Inyectar conteo real de productos activos
    for cat in categories:
        cat.active_product_count = Product.query.filter_by(
            category_id=cat.id,
            
            restaurant_id=restaurant.id,
            is_active=True
        ).count()
    
    # Obtener productos para el carrusel
    # 1. Prioridad: Marcados como destacados con imagen
    highlighted = Product.query.filter_by(
        restaurant_id=restaurant.id, 
        is_highlighted=True, 
        is_active=True
    ).filter(Product.image_url.isnot(None)).all()
    
    # 2. Fallback: Completar hasta 3 con los más recientes que tengan imagen
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
    
    # Limitar a 3 por si acaso
    highlighted_products = highlighted[:3]
    
    # 3. Obtener los 4 productos más recientes para la sección "Productos nuevos"
    new_products = Product.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).order_by(Product.created_at.desc()).limit(6).all()
    
    return render_template('public/menu_categories.html', 
                         categories=categories,
                         restaurant=restaurant,
                         ordering_disabled=ordering_disabled,
                         highlighted_products=highlighted_products,
                         new_products=new_products)

@public_bp.route('/menu/<string:slug>/categoria/<int:category_id>')
def category_products(slug, category_id):
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    
    category = Category.query.filter_by(id=category_id, restaurant_id=restaurant.id).first_or_404()
    
    products = Product.query.filter_by(
        category_id=category_id,
        restaurant_id=restaurant.id,
        is_active=True
    ).all()
    
    # Bloqueo Radical: Si el local está cerrado por el dueño, mostramos la Landing de Cerrado
    if not restaurant.is_open:
        return render_template('public/store_closed.html', restaurant=restaurant)

    # Lógica de "Solo Lectura" por suscripción
    is_active_sub = restaurant.is_active and is_subscription_active(restaurant, include_grace_period=True)
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

    # 1. Validación de Honeypot (Anti-Bots)
    if data.get('user_secondary_email'):
        # Si el campo trampa está lleno, es un bot. Bloqueo silencioso o error de seguridad.
        return jsonify({'success': False, 'error': 'Actividad sospechosa detectada.'}), 403

    # 2. Validación de Tiempo (Time-to-Submit)
    # Un humano tarda al menos 3 segundos en llenar el formulario.
    start_time = session.get('checkout_start_time', 0)
    if time.time() - start_time < 3.0:
        return jsonify({
            'success': False, 
            'error': '¡Uy, vas muy rápido! Tómate un segundo para revisar tus datos.'
        }), 429

    restaurant = Restaurant.query.filter_by(id=data.get('restaurant_id', 1)).first()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    if not restaurant.is_open:
        return jsonify({
            'success': False, 
            'error': 'Estamos cerrados en este momento. ¡Vuelve pronto!'
        }), 403
    
    # Validación estricta de suscripción (Backend)
    if not (restaurant.is_active and is_subscription_active(restaurant, include_grace_period=True)):
        return jsonify({
            'success': False, 
            'error': 'Pedidos temporalmente desactivados.'
        }), 403

    expiration_limit = datetime.now(timezone.utc) - timedelta(minutes=30)
    Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.status == 'pending',
        Order.created_at < expiration_limit
    ).update({Order.status: 'expired'})
    db.session.commit()

    client_ip = request.remote_addr
    
    should_block, error_message, wait_time = OrderRateLimiter.should_block_request(
        restaurant.id, client_ip
    )
    
    if should_block:
        return jsonify({
            'success': False,
            'error': error_message,
            'retry_after': wait_time
        }), 429

    order_number = generate_order_number(restaurant.id)
    
    notes = data.get('notes', 'Pedido realizado desde el menú digital.')
    customer_name = data.get('customer_name', 'Cliente Web')
    customer_phone = data.get('customer_phone', '')
    city = data.get('city')
    address = data.get('address')
    
    # Obtener información de la mesa si existe
    table_id = session.get('table_id') if session.get('restaurant_id') == restaurant.id else None
    table_name = None
    if table_id:
        table = Table.query.get(table_id)
        if table:
            table_name = table.name

    if table_name:
        notes = f"MESA: {table_name.upper()}\nTeléfono: {customer_phone}\n---\n{notes}"
    elif city and address:
        notes = f"ENTREGA EN: {city.upper()} - {address}\nTeléfono: {customer_phone}\n---\n{notes}"
    else:
        notes = f"Teléfono de Contacto: {customer_phone}\n---\n{notes}"

    # Creamos la orden con total 0 inicialmente, lo calcularemos en el servidor
    order = Order(
        restaurant_id=restaurant.id,
        order_number=order_number,
        status='pending',
        total=0, 
        customer_name=customer_name,
        customer_phone=customer_phone,
        notes=notes,
        table_id=table_id
    )
    db.session.add(order)
    db.session.flush()
    
    OrderRateLimiter.log_order_attempt(restaurant.id, order, client_ip)

    cart = data['cart']
    order_total = 0
    validated_items = []

    for product_id, item in cart.items():
        # 1. Validar Producto en DB
        product = Product.query.filter_by(id=product_id, restaurant_id=restaurant.id, is_active=True).first()
        if not product:
            continue # O manejar error si el producto ya no existe

        item_price = product.price
        extras_price = 0
        modifiers_data = []

        # 2. Validar Modificadores en DB
        for extra in item.get('extras', []):
            modifier_id = extra.get('id')
            if not modifier_id: continue
            
            modifier = Modifier.query.filter_by(id=modifier_id, product_id=product.id, is_active=True).first()
            if modifier:
                extras_price += modifier.extra_price
                modifiers_data.append({
                    'name': modifier.name,
                    'price': modifier.extra_price
                })

        subtotal = (item_price + extras_price) * item['quantity']
        order_total += subtotal

        order_item = OrderItem(
            order_id=order.id,
            restaurant_id=restaurant.id,
            product_name=product.name,
            product_price=item_price,
            quantity=item['quantity'],
            modifiers_snapshot=json.dumps(modifiers_data),
            subtotal=subtotal
        )
        db.session.add(order_item)
        
        validated_items.append({
            'name': product.name,
            'qty': item['quantity'],
            'extras': [m['name'] for m in modifiers_data]
        })

    # 3. Actualizar total final validado
    order.total = order_total
    db.session.commit()
    
    # 3. Actualizar total final validado
    order.total = order_total
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'order_number': order_number,
        'order_id': order.id,
        'total': order_total,
        'items': validated_items,
        'customer_name': customer_name,
        'address_full': f"{address}, {city}" if address and city else None,
        'table_name': order.table.name if order.table else None
    })

@public_bp.route('/menu/<string:slug>/novedades')
def novedades(slug):
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    categories = Category.query.filter_by(restaurant_id=restaurant.id).all()
    
    # Paginación
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    pagination = Product.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    products = pagination.items
    
    return render_template('public/menu_novedades.html',
                         restaurant=restaurant,
                         categories=categories,
                         products=products,
                         pagination=pagination)

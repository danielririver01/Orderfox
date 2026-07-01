from flask import Blueprint, render_template, abort, request, jsonify, redirect, url_for, session, send_from_directory
from app.models import db, Restaurant, Table
from app import csrf
from datetime import datetime
from app.utils.rate_limiter import OrderRateLimiter
from app.services.order_service import OrderService
from app.services.public_menu_service import PublicMenuService
from app.services.notification_service import notify_new_order
import time
import os

public_bp = Blueprint('public', __name__)

@public_bp.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@public_bp.route('/menu/api/init-checkout', methods=['POST'])
def init_checkout():
    """Registra el inicio del proceso de checkout en la sesión del usuario para anti-bots."""
    session['checkout_start_time'] = time.time()
    return jsonify({'success': True})

@public_bp.route('/menu/<string:slug>')
@public_bp.route('/menu')
def menu(slug=None):
    # Si no hay slug, buscar el primero activo (MVP)
    if not slug:
        restaurant = Restaurant.query.first()
        if not restaurant:
            abort(404)
        return redirect(url_for('public.menu', slug=restaurant.slug, **request.args))

    restaurant, error = PublicMenuService.get_restaurant_by_slug(slug)
    if error:
        abort(404)

    table_id = request.args.get('table')
    if table_id:
        table, _ = PublicMenuService.get_restaurant_table(restaurant, table_id)
        if table:
            session['table_id'] = table.id
            session['restaurant_id'] = restaurant.id
        else:
            session.pop('table_id', None)
            session.pop('restaurant_id', None)

    # Bloqueo Radical: Si el local está cerrado por el dueño, mostramos la Landing de Cerrado
    if not restaurant.is_open:
        return render_template('public/store_closed.html', restaurant=restaurant)

    ordering_disabled = not PublicMenuService.is_ordering_enabled(restaurant)
    categories = PublicMenuService.get_menu_categories_with_products(restaurant)

    return render_template('public/menu_public.html',
                         categories=categories,
                         restaurant=restaurant,
                         ordering_disabled=ordering_disabled)

@public_bp.route('/menu/<string:slug>/categoria/<int:category_id>')
def category_products(slug, category_id):
    """Redirect a la vista unificada del menú con anclaje a la categoría."""
    return redirect(url_for('public.menu', slug=slug) + f'#cat-{category_id}')

@public_bp.route('/menu/api/order', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'cart' not in data:
        return jsonify({'success': False, 'error': 'Carrito vacío'}), 400

    # 1. Validación de Honeypot (Anti-Bots)
    if data.get('user_secondary_email'):
        return jsonify({'success': False, 'error': 'Actividad sospechosa detectada.'}), 403

    # 2. Validación de Tiempo (Time-to-Submit)
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
    if not PublicMenuService.is_ordering_enabled(restaurant):
        return jsonify({
            'success': False,
            'error': 'Pedidos temporalmente desactivados.'
        }), 403

    # Expirar pedidos pendientes antiguos
    PublicMenuService.expire_old_pending_orders(restaurant.id, minutes=30)

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

    order_number = OrderService.generate_order_number(restaurant.id)

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

    # Construir notas del pedido
    notes = PublicMenuService.build_order_notes(
        customer_phone=customer_phone,
        table_name=table_name,
        city=city,
        address=address,
        notes=notes,
    )

    # Crear el pedido con los items del carrito
    order, validated_items, total_or_error = PublicMenuService.create_order_from_cart(
        restaurant=restaurant,
        cart=data['cart'],
        customer_name=customer_name,
        customer_phone=customer_phone,
        notes=notes,
        table_id=table_id,
        ip_address=client_ip,
        order_number=order_number,
    )

    if order is None:
        return jsonify({
            'success': False,
            'error': total_or_error.get('message', 'Error al crear el pedido.')
        }), 500

    order_id = order.id
    notify_new_order(order_id)

    return jsonify({
        'success': True,
        'order_number': order_number,
        'order_id': order_id,
        'total': total_or_error,
        'items': validated_items,
        'customer_name': customer_name,
        'address_full': f"{address}, {city}" if address and city else None,
        'table_name': order.table.name if order.table else None
    })

@public_bp.route('/menu/<string:slug>/novedades')
def novedades(slug):
    """Redirect a la vista unificada del menú."""
    return redirect(url_for('public.menu', slug=slug))

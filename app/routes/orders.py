from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from app.models import db, Product
from app.utils.auth import login_required, active_required
import json

from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_feature_access
from app.services.order_service import OrderService
from app.services.notification_service import notify_new_order

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')

@orders_bp.route('/')
@login_required
@active_required
def index():
    """Listar pedidos: activos sin filtro de fecha, completados solo hoy"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)

    sort_order = request.args.get('sort', 'asc')

    all_orders = OrderService.get_combined_orders(restaurant.id, sort_order)

    pending = [o for o in all_orders if o.status == 'pending']
    confirmed = [o for o in all_orders if o.status == 'confirmed']
    delivered = [o for o in all_orders if o.status == 'delivered']
    cancelled = [o for o in all_orders if o.status == 'cancelled']

    last_order_id = all_orders[0].id if all_orders else 0
    
    return render_template('dashboard/orders.html', 
                         pending=pending, 
                         confirmed=confirmed, 
                         delivered=delivered,
                         cancelled=cancelled,
                         last_order_id=last_order_id)

@orders_bp.route('/fragment')
@login_required
@active_required
def fragment():
    """Devuelve solo el HTML de la lista de pedidos para actualizaciones AJAX."""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)

    sort_order = request.args.get('sort', 'asc')

    all_orders = OrderService.get_combined_orders(restaurant.id, sort_order)

    pending = [o for o in all_orders if o.status == 'pending']
    confirmed = [o for o in all_orders if o.status == 'confirmed']
    delivered = [o for o in all_orders if o.status == 'delivered']
    cancelled = [o for o in all_orders if o.status == 'cancelled']

    return render_template('dashboard/_orders_list.html',
                           pending=pending,
                           confirmed=confirmed,
                           delivered=delivered,
                           cancelled=cancelled)


@orders_bp.route('/create', methods=['GET', 'POST'])
@login_required
@active_required
def create():
    """Crear nuevo pedido (simplificado para MVP)"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    if request.method == 'POST':
        data = request.form

        order_data = {
            'customer_name': data.get('customer_name'),
            'customer_phone': data.get('customer_phone', ''),
            'notes': data.get('notes', ''),
            'pending_expiry_hours': restaurant.pending_expiry_hours or 24,
        }

        order = OrderService.create_order(restaurant.id, order_data)

        items_data = json.loads(data.get('items', '[]'))
        total, _ = OrderService.add_items_to_order(order, items_data, restaurant.id)

        db.session.commit()
        notify_new_order(order.id)
        return redirect(url_for('orders.index'))
    
    products = Product.query.filter_by(restaurant_id=restaurant.id, is_active=True).all()
    return render_template('dashboard/order_create.html', products=products)

@orders_bp.route('/<int:id>')
@login_required
@active_required
def detail(id):
    """Ver detalle de un pedido"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    return render_template('dashboard/order_detail.html', order=order)

@orders_bp.route('/<int:id>/fragment')
@login_required
@active_required
def detail_fragment(id):
    """Devuelve solo el HTML del detalle del pedido para el panel lateral"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    return render_template('dashboard/_order_detail_fragment.html', order=order)

@orders_bp.route('/<int:id>/status', methods=['PATCH'])
@login_required
@active_required
def change_status(id):
    """Cambiar estado del pedido"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)

    data = request.get_json()
    new_status = data.get('status')

    if not check_feature_access(restaurant, 'has_status_management') and new_status not in ['confirmed', 'cancelled', 'pending']:
         return jsonify({
            'success': False, 
            'error': f'Tu plan {restaurant.plan_type.capitalize()} no permite marcar pedidos como Entregados. ¡Actualiza a Crecimiento para control total!'
        }), 403

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    
    if not OrderService.validate_status_transition(order.status, new_status):
        return jsonify({
            'success': False, 
            'error': f'No se puede cambiar de {order.status} a {new_status}'
        }), 400
    
    order.status = new_status
    db.session.commit()
    
    return jsonify({'success': True, 'status': order.status})

@orders_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@active_required
def cancel(id):
    """Cancelar pedido"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    
    if order.status in ['delivered', 'cancelled']:
        flash('No se puede cancelar un pedido entregado o ya cancelado', 'error')
        return redirect(url_for('orders.detail', id=id))
    
    order.status = 'cancelled'
    db.session.commit()
    
    return redirect(url_for('orders.index'))

@orders_bp.route('/<int:id>/receipt')
@login_required
@active_required
def receipt(id):
    """Generar vista de recibo para impresión"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    return render_template('dashboard/receipt.html', order=order, restaurant=restaurant)

@orders_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@active_required
def delete(id):
    """Eliminar pedido permanentemente"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    
    # Solo permitir eliminar si está cancelado (regla de negocio sugerida)
    if order.status != 'cancelled':
        flash('Solo se pueden eliminar pedidos que ya han sido cancelados', 'error')
        return redirect(url_for('orders.detail', id=id))
        
    db.session.delete(order)
    db.session.commit()
    
    flash('Pedido eliminado correctamente', 'success')
    return redirect(url_for('orders.index'))

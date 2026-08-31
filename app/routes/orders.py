from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from app.models import db, OrderEvent
from app.utils.auth import (
    require_auth, require_active, require_role, require_role_check,
)
import json

from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_feature_access
from app.services.order_service import (
    OrderService,
    PaymentValidationError,
    log_event,
    resolve_actor,
    serialize_event,
)
from app.services.notification_service import notify_new_order

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')

# Endpoints de /orders/* que usan los empleados desde su portal (v2.1.1):
# - orders.change_status     → mesero (y cajero): cambiar estado del pedido
# - orders.register_payment  → cajero (y dueño): registrar pago
# El resto de rutas de /orders/* es solo del dueño.
_EMPLOYEE_ALLOWED_ENDPOINTS = {'orders.change_status', 'orders.register_payment'}


@orders_bp.before_request
def _require_dashboard_owner():
    """Bloquea empleados en las rutas de pedidos del dashboard, salvo los
    endpoints que usan desde su portal (v2.1.1)."""
    if request.endpoint in _EMPLOYEE_ALLOWED_ENDPOINTS:
        return None
    return require_role_check('owner')

@orders_bp.route('/')
@require_auth
@require_active
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
@require_auth
@require_active
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
@require_auth
@require_active
@require_role('owner')
def create():
    """Crear nuevo pedido (simplificado para MVP). Solo dueño: los empleados
    usan su propia ruta POS (employee_portal.order_create)."""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    if request.method == 'POST':
        data = request.form

        order_data = {
            'customer_name': data.get('customer_name', ''),
            'customer_phone': data.get('customer_phone', ''),
            'notes': data.get('notes', ''),
            'pending_expiry_hours': restaurant.pending_expiry_hours or 24,
        }

        try:
            order = OrderService.create_order(restaurant.id, order_data)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
            return redirect(url_for('orders.create'))

        items_data = json.loads(data.get('items', '[]'))
        try:
            total, _ = OrderService.add_items_to_order(order, items_data, restaurant.id)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
            return redirect(url_for('orders.create'))

        actor_id, actor_role = resolve_actor()
        log_event(order.id, 'order_created', actor_id=actor_id, actor_role=actor_role)

        # Pago opcional (modal caja registradora)
        payment_method = data.get('payment_method') or None
        if payment_method:
            amount_raw = data.get('amount_received') or None
            try:
                amount = int(amount_raw) if amount_raw else None
            except (TypeError, ValueError):
                amount = None
            try:
                log_event(order.id, 'payment_registered', actor_id=actor_id,
                          actor_role=actor_role,
                          metadata={'method': payment_method, 'amount': amount})
                OrderService.record_payment(order, payment_method, amount_received=amount)
            except PaymentValidationError as e:
                db.session.rollback()
                flash(str(e), 'error')
                return redirect(url_for('orders.create'))

        db.session.commit()
        notify_new_order(order.id)
        return redirect(url_for('orders.index'))
    
    products = OrderService.get_active_products(restaurant.id)
    return render_template('dashboard/order_create.html', products=products)

@orders_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@require_auth
@require_active
def edit(id):
    """Editar los items y datos de una venta (solo pedidos no cancelados)."""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    if order.status == 'cancelled':
        flash('No se puede editar un pedido cancelado', 'error')
        return redirect(url_for('orders.detail', id=id))

    if request.method == 'POST':
        data = request.form

        if data.get('customer_name'):
            order.customer_name = data.get('customer_name')
        order.customer_phone = data.get('customer_phone', '')
        order.notes = data.get('notes', '')

        items_data = json.loads(data.get('items', '[]'))

        # Edición de pago (modal caja registradora en la pantalla de edición).
        payment_method = data.get('payment_method') or None
        amount_raw = data.get('amount_received') or None
        try:
            amount = int(amount_raw) if amount_raw else None
        except (TypeError, ValueError):
            amount = None

        # Traza items_edited ANTES de actualizar (update_order_items hace commit
        # interno; si falla, hace rollback y el evento se descarta con él).
        actor_id, actor_role = resolve_actor()
        try:
            before_items = {item.product_name: item.quantity for item in order.items}
            id_to_name = {p.id: p.name for p in OrderService.get_active_products(restaurant.id)}
            new_items = {}
            for it in items_data:
                qty = it.get('quantity', 1)
                if not qty:
                    continue
                name = id_to_name.get(it.get('product_id'))
                if name:
                    new_items[name] = new_items.get(name, 0) + int(qty)
            added = [
                {'name': n, 'qty': q}
                for n, q in new_items.items() if q > before_items.get(n, 0)
            ]
            removed = [
                {'name': n, 'qty': q}
                for n, q in before_items.items() if q > new_items.get(n, 0)
            ]
            if added or removed:
                log_event(order.id, 'items_edited', actor_id=actor_id,
                          actor_role=actor_role,
                          metadata={'added': added, 'removed': removed})
        except (TypeError, ValueError):
            pass

        try:
            OrderService.update_order_items(
                order, items_data, restaurant.id,
                payment_method=payment_method, amount_received=amount,
            )
        except (ValueError, PaymentValidationError) as e:
            db.session.rollback()
            flash(str(e), 'error')
            return redirect(url_for('orders.edit', id=id))

        flash('Venta actualizada correctamente', 'success')
        return redirect(url_for('orders.detail', id=id))

    products = OrderService.get_active_products(restaurant.id)
    # Mapear los items actuales del pedido a product_id para precargar el carrito.
    name_to_id = {p.name: p.id for p in products}
    order_items_json = json.dumps([
        {'product_id': name_to_id[item.product_name], 'quantity': item.quantity}
        for item in order.items if item.product_name in name_to_id
    ])
    return render_template('dashboard/order_edit.html', order=order,
                           products=products, order_items_json=order_items_json)


@orders_bp.route('/<int:id>')
@require_auth
@require_active
def detail(id):
    """Ver detalle de un pedido"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    events = [serialize_event(e) for e in OrderEvent.query
              .filter_by(order_id=order.id)
              .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc()).all()]
    return render_template('dashboard/order_detail.html', order=order, events=events)

@orders_bp.route('/<int:id>/fragment')
@require_auth
@require_active
def detail_fragment(id):
    """Devuelve solo el HTML del detalle del pedido para el panel lateral"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    return render_template('dashboard/_order_detail_fragment.html', order=order)

@orders_bp.route('/<int:id>/status', methods=['PATCH'])
@require_auth
@require_active
@require_role('owner', 'cashier', 'waiter')
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

    actor_id, actor_role = resolve_actor()
    if order.status == 'cancelled' and new_status == 'pending':
        log_event(order.id, 'order_restored', actor_id=actor_id, actor_role=actor_role,
                  metadata={'from': order.status, 'to': new_status})
    elif new_status == 'cancelled':
        log_event(order.id, 'order_cancelled', actor_id=actor_id, actor_role=actor_role,
                  metadata={'from': order.status, 'to': new_status})
    else:
        log_event(order.id, 'status_changed', actor_id=actor_id, actor_role=actor_role,
                  metadata={'from': order.status, 'to': new_status})

    OrderService.change_order_status(order, new_status)
    return jsonify({'success': True, 'status': order.status})


@orders_bp.route('/<int:id>/payment', methods=['POST'])
@require_auth
@require_active
@require_role('owner', 'cashier')
def register_payment(id):
    """Registrar el pago de un pedido (modal caja registradora).

    Responde JSON porque se consume desde fetch() en el modal:
    - 200 {success, data: {payment_method, amount_received, change_due, paid_at}}
    - 400 {success: False, error} para errores de negocio (monto insuficiente, método inválido)
    - 409 {success: False, error} si el pedido ya tiene pago registrado
    """
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)

    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)

    data = request.get_json(silent=True) or {}
    method = data.get('payment_method') or data.get('method')
    amount_raw = data.get('amount_received') or data.get('amount')
    try:
        amount = int(amount_raw) if amount_raw else None
    except (TypeError, ValueError):
        amount = None

    try:
        actor_id, actor_role = resolve_actor()
        log_event(order.id, 'payment_registered', actor_id=actor_id,
                  actor_role=actor_role,
                  metadata={'method': method, 'amount': amount})
        order, change = OrderService.record_payment(order, method, amount_received=amount)
    except PaymentValidationError as e:
        return jsonify({'success': False, 'error': str(e)}), e.status_code
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Error al registrar el pago'}), 500

    return jsonify({
        'success': True,
        'data': {
            'order_id': order.id,
            'payment_method': order.payment_method,
            'amount_received': order.amount_received,
            'change_due': order.change_due,
            'paid_at': order.paid_at.isoformat() if order.paid_at else None
        }
    })

@orders_bp.route('/<int:id>/cancel', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def cancel(id):
    """Cancelar pedido"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)

    actor_id, actor_role = resolve_actor()
    if order.status != 'cancelled':
        log_event(order.id, 'order_cancelled', actor_id=actor_id, actor_role=actor_role,
                  metadata={'from': order.status, 'to': 'cancelled'})

    success, error = OrderService.cancel_order(order)
    if not success:
        flash(error, 'error')
        return redirect(url_for('orders.detail', id=id))
    
    return redirect(url_for('orders.index'))

@orders_bp.route('/<int:id>/receipt')
@require_auth
@require_active
def receipt(id):
    """Generar vista de recibo para impresión"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    return render_template('dashboard/receipt.html', order=order, restaurant=restaurant)

@orders_bp.route('/<int:id>/delete', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def delete(id):
    """Eliminar pedido permanentemente"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    order = OrderService.get_order_for_restaurant(restaurant.id, id)
    if not order: abort(404)
    
    success, error = OrderService.delete_order(order)
    if not success:
        flash(error, 'error')
        return redirect(url_for('orders.detail', id=id))
    
    flash('Pedido eliminado correctamente', 'success')
    return redirect(url_for('orders.index'))

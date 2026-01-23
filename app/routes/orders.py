from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from app.models import db, Order, OrderItem, Product
from datetime import datetime, date
import json

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')

# Temporal: Hardcoded restaurant_id
TEMP_RESTAURANT_ID = 1

def generate_order_number(restaurant_id):
    """Generar número de orden secuencial para el día (ORD-001, ORD-002...)"""
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    
    # Contar pedidos de hoy
    count = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.created_at >= today_start
    ).count()
    
    return f"ORD-{count + 1:03d}"

def validate_status_transition(current_status, new_status):
    """Validar que la transición de estado sea válida"""
    valid_transitions = {
        'pending': ['kitchen', 'cancelled'],
        'kitchen': ['delivered', 'cancelled'],
        'delivered': [],  # No se puede cambiar desde entregado
        'cancelled': []   # No se puede cambiar desde cancelado
    }
    
    return new_status in valid_transitions.get(current_status, [])

@orders_bp.route('/')
def index():
    """Listar pedidos del día agrupados por estado"""
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    
    # Obtener pedidos de hoy
    orders = Order.query.filter(
        Order.restaurant_id == TEMP_RESTAURANT_ID,
        Order.created_at >= today_start
    ).order_by(Order.created_at.desc()).all()
    
    # Agrupar por estado
    pending = [o for o in orders if o.status == 'pending']
    kitchen = [o for o in orders if o.status == 'kitchen']
    delivered = [o for o in orders if o.status == 'delivered']
    
    return render_template('dashboard/orders.html', 
                         pending=pending, 
                         kitchen=kitchen, 
                         delivered=delivered)

@orders_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Crear nuevo pedido (simplificado para MVP)"""
    if request.method == 'POST':
        data = request.form
        
        # Generar número de orden
        order_number = generate_order_number(TEMP_RESTAURANT_ID)
        
        # Crear orden
        order = Order(
            restaurant_id=TEMP_RESTAURANT_ID,
            order_number=order_number,
            customer_name=data.get('customer_name'),
            customer_phone=data.get('customer_phone'),
            notes=data.get('notes'),
            total=0,  # Se calculará después
            status='pending'
        )
        db.session.add(order)
        db.session.flush()  # Para obtener el ID
        
        # Agregar items (simplificado - en producción vendría del carrito)
        # Por ahora, asumimos que viene un JSON con los items
        items_data = json.loads(data.get('items', '[]'))
        total = 0
        
        for item_data in items_data:
            # Obtener producto para snapshot
            product = Product.query.get(item_data['product_id'])
            if not product:
                continue
            
            # Calcular subtotal
            subtotal = product.price * item_data.get('quantity', 1)
            
            # Agregar modificadores si hay
            modifiers = []
            if 'modifiers' in item_data:
                for mod_id in item_data['modifiers']:
                    # Aquí iría la lógica de modificadores
                    pass
            
            order_item = OrderItem(
                order_id=order.id,
                product_name=product.name,
                product_price=product.price,
                quantity=item_data.get('quantity', 1),
                modifiers_snapshot=json.dumps(modifiers) if modifiers else None,
                subtotal=subtotal
            )
            db.session.add(order_item)
            total += subtotal
        
        # Actualizar total
        order.total = total
        db.session.commit()
        
        flash(f'Pedido {order_number} creado exitosamente', 'success')
        return redirect(url_for('orders.detail', id=order.id))
    
    # GET: Mostrar formulario
    products = Product.query.filter_by(restaurant_id=TEMP_RESTAURANT_ID, is_active=True).all()
    return render_template('dashboard/order_create.html', products=products)

@orders_bp.route('/<int:id>')
def detail(id):
    """Ver detalle de un pedido"""
    order = Order.query.filter_by(id=id, restaurant_id=TEMP_RESTAURANT_ID).first_or_404()
    return render_template('dashboard/order_detail.html', order=order)

@orders_bp.route('/<int:id>/status', methods=['PATCH'])
def change_status(id):
    """Cambiar estado del pedido"""
    order = Order.query.filter_by(id=id, restaurant_id=TEMP_RESTAURANT_ID).first_or_404()
    
    data = request.get_json()
    new_status = data.get('status')
    
    # Validar transición
    if not validate_status_transition(order.status, new_status):
        return jsonify({
            'success': False, 
            'error': f'No se puede cambiar de {order.status} a {new_status}'
        }), 400
    
    order.status = new_status
    db.session.commit()
    
    return jsonify({'success': True, 'status': order.status})

@orders_bp.route('/<int:id>/cancel', methods=['POST'])
def cancel(id):
    """Cancelar pedido"""
    order = Order.query.filter_by(id=id, restaurant_id=TEMP_RESTAURANT_ID).first_or_404()
    
    # Validar que se pueda cancelar
    if order.status in ['delivered', 'cancelled']:
        flash('No se puede cancelar un pedido entregado o ya cancelado', 'error')
        return redirect(url_for('orders.detail', id=id))
    
    order.status = 'cancelled'
    db.session.commit()
    
    flash(f'Pedido {order.order_number} cancelado', 'success')
    return redirect(url_for('orders.index'))

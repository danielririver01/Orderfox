from flask import Blueprint, render_template, request, jsonify, abort
from app.utils.auth import login_required
from app.models import db, Order
from datetime import date, datetime
from sqlalchemy import func

from app.utils.restaurant import get_current_restaurant

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    
    # Obtener conteos por estado para hoy
    stats = db.session.query(
        Order.status, 
        func.count(Order.id)
    ).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start
    ).group_by(Order.status).all()
    
    # Convertir a diccionario
    counts = {s: c for s, c in stats}
    pending_count = counts.get('pending', 0)
    confirmed_count = counts.get('confirmed', 0)
    delivered_count = counts.get('delivered', 0)
    
    # Calcular ventas totales hoy (solo pedidos no cancelados)
    total_sales = db.session.query(func.sum(Order.total)).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start,
        Order.status != 'cancelled'
    ).scalar() or 0
    
    return render_template('dashboard/index.html', 
                         restaurant=restaurant,
                         pending_count=pending_count,
                         confirmed_count=confirmed_count,
                         delivered_count=delivered_count,
                         total_sales=f"{int(total_sales):,}",
                         is_open=restaurant.is_active)

@dashboard_bp.route('/toggle-status', methods=['POST'])
@login_required
def toggle_status():
    restaurant = get_current_restaurant()
    if not restaurant: return jsonify({'success': False}), 404
    
    data = request.get_json()
    new_status = data.get('is_open', True)
    
    restaurant.is_active = new_status
    db.session.commit()
    
    return jsonify({'success': True, 'is_open': restaurant.is_active})

@dashboard_bp.route('/Productos')
@login_required
def productos():
    return render_template('dashboard/productos.html')

@dashboard_bp.route('/settings')
@login_required
def settings():
    from flask import session
    from app.models import User
    
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    user = User.query.get(session.get('user_id'))
    
    return render_template('dashboard/settings.html', 
                         restaurant=restaurant,
                         user=user)


from flask import Blueprint, render_template, request, jsonify, abort, send_file, url_for
from app.utils.auth import login_required
from app.models import db, Order
from datetime import date, datetime
from sqlalchemy import func
import qrcode 
from io import BytesIO
from PIL import Image

from app.utils.restaurant import get_current_restaurant

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # En desarrollo esto devuelve localhost:5000, en producción devuelve el dominio real.
    # Si el usuario quiere forzar un dominio específico en producción, se puede configurar aquí.
    menu_url = url_for('public.menu', slug=restaurant.slug, _external=True)
    
    # Reemplazo de seguridad para dominios específicos si _external no es suficiente
    # if not request.host.startswith('127.0.0.1') and not request.host.startswith('localhost'):
    #     menu_url = menu_url.replace(request.host, 'velzi.xyz') # Ejemplo de dominio real
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
                         is_open=restaurant.is_active,
                         menu_url=menu_url)

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
    
    return render_template('dashboard/settings.html', restaurant=restaurant, user=user)

@dashboard_bp.route('/menu/<slug>/qr')
@login_required
def menu_qr(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # Generar URL completa del menú
    menu_url = url_for('public.menu', slug=slug, _external=True)
    
    # Generar URL de la imagen QR
    qr_image_url = url_for('dashboard.menu_qr_image', slug=slug)
    
    return render_template('dashboard/qr_page.html', 
                         restaurant=restaurant, 
                         menu_url=menu_url,
                         qr_image_url=qr_image_url,
                         slug=slug)

@dashboard_bp.route('/menu/<slug>/qr_image.png')
def menu_qr_image(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # Generar URL completa del menú
    menu_url = url_for('public.menu', slug=slug, _external=True)
    
    # Crear QR con configuración óptima
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    
    # Generar imagen
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img_io = BytesIO()
    img.save(img_io, format="PNG")
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png', as_attachment=False)

@dashboard_bp.route('/menu/<slug>/qr/download')
@login_required
def menu_qr_download(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # Obtener formato desde query params (default: png)
    fmt = request.args.get('format', 'png').lower()
    
    # Validar formato
    if fmt not in ['png', 'jpg', 'jpeg']:
        return jsonify({'error': 'Formato no soportado. Use: png, jpg o jpeg'}), 400
    
    # Generar URL completa del menú
    menu_url = url_for('public.menu', slug=slug, _external=True)
    
    # Crear QR con alta calidad para descarga
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # Mayor corrección de errores
        box_size=10,
        border=4,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    
    # Generar imagen
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = BytesIO()
    
    # Guardar según formato
    if fmt == 'png':
        img.save(buf, format='PNG')
        mime_type = 'image/png'
    else:  # jpg o jpeg
        img.save(buf, format='JPEG', quality=95)
        mime_type = 'image/jpeg'
    
    buf.seek(0)
    file_name = f"qr-{slug}.{fmt}"
    
    return send_file(buf, mimetype=mime_type, as_attachment=True, download_name=file_name)
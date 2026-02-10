from flask import (
    Blueprint, 
    render_template, 
    request, 
    jsonify, 
    abort, 
    send_file, 
    url_for,
    flash,
    redirect,
    redirect,
    session,
    current_app
)
from app.utils.auth import login_required, active_required
from app.models import db, Order, Restaurant, User
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import func
import qrcode 
from io import BytesIO
from PIL import Image
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import (
    check_feature_access,
    get_plan_limits,
    PLAN_LIMITS,
    get_subscription_status
)
import re
import unicodedata

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
@active_required
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
                         is_open=restaurant.is_open,
                         menu_url=menu_url)

@dashboard_bp.route('/toggle-status', methods=['POST'])
@login_required
@active_required
def toggle_status():
    restaurant = get_current_restaurant()
    if not restaurant: return jsonify({'success': False}), 404
    
    # Validar permisos (Upselling)
    has_status_access = check_feature_access(restaurant, 'has_status_management')
    if not has_status_access:
        return jsonify({
            'success': False,
            'error': 'upgrade_required',
            'message': '🔒 Esta función es Premium. Actualiza tu plan para controlar el horario de tu tienda.'
        }), 403

    data = request.get_json()
    new_status = data.get('is_open', True)
    
    restaurant.is_open = new_status
    db.session.commit()
    
    return jsonify({'success': True, 'is_open': restaurant.is_open})

@dashboard_bp.route('/Productos')
@login_required
@active_required
def productos():
    return render_template('dashboard/productos.html')

@dashboard_bp.route('/settings')
@login_required
@active_required
def settings():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    user = User.query.get(session.get('user_id'))
    
    # Fuente única de verdad para el estado de suscripción
    sub_status = get_subscription_status(restaurant)
    
    # Verificar acceso a características
    has_qr = check_feature_access(restaurant, 'has_qr')
    
    return render_template('dashboard/settings.html', 
                         restaurant=restaurant, 
                         user=user, 
                         has_qr=has_qr,
                         sub_status=sub_status)

@dashboard_bp.route('/menu/<slug>/qr')
@login_required
@active_required
def menu_qr(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # Verificar acceso a QR para UI
    has_qr_access = check_feature_access(restaurant, 'has_qr')
    
    # Generar URL completa del menú
    # Generar URL completa del menú usando BASE_URL
    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    menu_url = f"{base_url}/menu/{slug}"
    
    # Generar URL de la imagen QR (funcionará para mostrarla visualmente, 
    # pero la descarga estará protegida)
    qr_image_url = url_for('dashboard.menu_qr_image', slug=slug)
    
    return render_template('dashboard/qr_page.html', 
                         restaurant=restaurant, 
                         menu_url=menu_url,
                         qr_image_url=qr_image_url,
                         slug=slug,
                         has_qr_access=has_qr_access)

@dashboard_bp.route('/menu/<slug>/qr_image.png')
def menu_qr_image(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    if check_feature_access(restaurant, 'has_qr'):
        base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
        menu_url = f"{base_url}/menu/{slug}"
    else:
        menu_url = "https://velzia.com/upgrade?utm_source=qr_lock" 
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img_io = BytesIO()
    img.save(img_io, format="PNG")
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png', as_attachment=False)

@dashboard_bp.route('/menu/<slug>/qr/download')
@login_required
@active_required
def menu_qr_download(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)

    if not check_feature_access(restaurant, 'has_qr'):
        abort(403)
    
    fmt = request.args.get('format', 'png').lower()
    
    if fmt not in ['png', 'jpg', 'jpeg']:
        return jsonify({'error': 'Formato no soportado. Use: png, jpg o jpeg'}), 400
    
    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    menu_url = f"{base_url}/menu/{slug}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # Mayor corrección de errores
        box_size=10,
        border=4,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = BytesIO()
    
    if fmt == 'png':
        img.save(buf, format='PNG')
        mime_type = 'image/png'
    else:  # jpg o jpeg
        img.save(buf, format='JPEG', quality=95)
        mime_type = 'image/jpeg'
    
    buf.seek(0)
    # Generar nombre de archivo amigable basado en el nombre actual del restaurante
    # (No solo el slug inmutable de la URL)
    def slugify(text):
        text = str(text)
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^\w\s-]', '', text).strip().lower()
        return re.sub(r'[-\s]+', '-', text)

    friendly_name = slugify(restaurant.name)
    file_name = f"qr-{friendly_name}.{fmt}"
    
    return send_file(buf, mimetype=mime_type, as_attachment=True, download_name=file_name)

@dashboard_bp.route('/subscription')
@login_required
@active_required
def subscription():
    """
    Vista de gestión de suscripción.
    
    REGLA DE ORO: Este endpoint NO calcula nada.
    Solo consume get_subscription_status() y pasa los datos al template.
    """
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)
    
    user = User.query.get(session.get('user_id'))
    
    # FUENTE ÚNICA DE VERDAD: Obtener estado completo desde subscription.py
    sub_status = get_subscription_status(restaurant)
    
    # Límites del plan actual
    plan_info = get_plan_limits(restaurant.plan_type)
    
    # Fecha de creación del restaurante (formateada)
    created_date = "No disponible"
    if restaurant.created_at:
        # Si restaurant.created_at también es AwareDateTime, esto funcionará
        dt = restaurant.created_at
        meses_es = {
            1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
            5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
            9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
        }
        created_date = f"{dt.day} de {meses_es[dt.month]} de {dt.year}"
    
    # IMPORTANTE: No calculamos expiration_date aquí
    # Ya está en sub_status['formatted_expiration']
    
    return render_template(
        'dashboard/subscription.html',
        restaurant=restaurant,
        user=user,
        sub_status=sub_status,
        plan_info=plan_info,
        created_date=created_date
    )

@dashboard_bp.route('/delete-account', methods=['POST'])
@login_required
@active_required
def delete_account():
    restaurant = get_current_restaurant()
    if not restaurant: 
        return jsonify({'success': False, 'message': 'Restaurante no encontrado'}), 404
    
    try:
        # Eliminar el restaurante (cascade eliminará todos los datos relacionados)
        db.session.delete(restaurant)
        db.session.commit()
        
        session.clear()
        
        return jsonify({'success': True, 'message': 'Cuenta eliminada exitosamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al eliminar la cuenta'}), 500

@dashboard_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@active_required
def profile():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    user = User.query.get(session.get('user_id'))
    
    if request.method == 'POST':
        restaurant_name = request.form.get('restaurant_name')
        whatsapp_phone = request.form.get('whatsapp_phone')
        username = request.form.get('username')
        
        if not restaurant_name or not whatsapp_phone or not username:
            flash('Todos los campos son obligatorios.', 'error')
            return render_template('dashboard/profile_form.html', restaurant=restaurant, user=user)
        
        try:
            # Validar si el nombre del negocio ya existe en otro restaurante
            existing_restaurant = Restaurant.query.filter(
                Restaurant.name == restaurant_name, 
                Restaurant.id != restaurant.id
            ).first()
            
            if existing_restaurant:
                flash('Este nombre de negocio ya está en uso. Por favor, elige otro.', 'error')
                return render_template('dashboard/profile_form.html', restaurant=restaurant, user=user)

            existing_user = User.query.filter(
                User.username == username, 
                User.id != user.id
            ).first()
            
            if existing_user:
                flash('Este nombre de usuario ya está en uso. Por favor, elige otro.', 'error')
                return render_template('dashboard/profile_form.html', restaurant=restaurant, user=user)

            restaurant.name = restaurant_name
            restaurant.whatsapp_phone = whatsapp_phone
            user.username = username
            
            db.session.commit()
            flash('¡Perfil actualizado correctamente!', 'success')
            return redirect(url_for('dashboard.profile'))
        except Exception as e:
            db.session.rollback()
            flash('Error al actualizar el perfil. Intenta de nuevo.', 'error')
            print(f"Error updating profile: {e}")
            
    return render_template('dashboard/profile_form.html', 
                         restaurant=restaurant, 
                         user=user)

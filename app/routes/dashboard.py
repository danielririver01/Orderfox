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

import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
@active_required
def index():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    menu_url = url_for('public.menu', slug=restaurant.slug, _external=True)
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    stats = db.session.query(
        Order.status, 
        func.count(Order.id)
    ).filter(
        Order.restaurant_id == restaurant.id,
        Order.created_at >= today_start
    ).group_by(Order.status).all()
    counts = {s: c for s, c in stats}
    pending_count = counts.get('pending', 0)
    confirmed_count = counts.get('confirmed', 0)
    delivered_count = counts.get('delivered', 0)
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
    try:
        restaurant = get_current_restaurant()
        if not restaurant: 
            logger.warning("Settings accessed without active restaurant session")
            abort(404)
        
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        if not user:
            logger.error(f"Settings accessed by invalid user_id: {user_id}")
            session.clear()
            flash("Sesión inválida. Por favor inicia sesión nuevamente.", "error")
            return redirect(url_for('auth.login'))
            
        # Robust data fetching
        try:
            sub_status = get_subscription_status(restaurant)
        except Exception as e:
            logger.error(f"Error getting subscription status for restaurant {restaurant.id}: {e}")
            sub_status = None
            
        try:
            has_qr = check_feature_access(restaurant, 'has_qr')
        except Exception as e:
            logger.error(f"Error checking feature access for restaurant {restaurant.id}: {e}")
            has_qr = False
        
        # Ensure SUPPORT_PHONE is available even if context processor fails
        support_phone = current_app.config.get('SUPPORT_PHONE')
        if not support_phone:
            logger.warning("SUPPORT_PHONE environment variable missing in settings route")
            support_phone = "" 

        return render_template('dashboard/settings.html', 
                             restaurant=restaurant, 
                             user=user, 
                             has_qr=has_qr,
                             sub_status=sub_status,
                             SUPPORT_PHONE=support_phone)
                             
    except Exception as e:
        logger.exception("Unexpected error in settings route")
        abort(500)

@dashboard_bp.route('/menu/<slug>/qr')
@login_required
@active_required
def menu_qr(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    has_qr_access = True
    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    menu_url = f"{base_url}/menu/{slug}"
    qr_image_url = url_for('dashboard.menu_qr_image', slug=slug)
    
    return render_template('dashboard/qr_page.html', 
                         restaurant=restaurant, 
                         menu_url=menu_url,
                         qr_image_url=qr_image_url,
                         slug=slug,
                         has_qr_access=has_qr_access,
                         is_table_qr=False)

@dashboard_bp.route('/menu/<slug>/qr_image.png')
def menu_qr_image(slug):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # QR de restaurante siempre visible
    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    menu_url = f"{base_url}/menu/{slug}"
    
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
    # Generar nombre de archivo amigable basado en el nombre del restaurante
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
    Vista de gestión de suscripción. Consume get_subscription_status() centralizadamente.
    """
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)
    
    user = User.query.get(session.get('user_id'))
    
    user = User.query.get(session.get('user_id'))
    sub_status = get_subscription_status(restaurant)
    
    # Límites del plan actual
    plan_info = get_plan_limits(restaurant.plan_type)
    
    # Fecha de creación del restaurante (formateada)
    created_date = "No disponible"
    if restaurant.created_at:
        dt = restaurant.created_at
        meses_es = {
            1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
            5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
            9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
        }
        created_date = f"{dt.day} de {meses_es[dt.month]} de {dt.year}"
    
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
            existing_restaurant = Restaurant.query.filter(
                Restaurant.name == restaurant_name, 
                Restaurant.id != restaurant.id
            ).first()
            
            if existing_restaurant:
                flash('Este nombre de negocio ya está en uso. Por favor, elige otro.', 'error')
                return render_template('dashboard/profile_form.html', restaurant=restaurant, user=user)

            restaurant.name = restaurant_name
            restaurant.whatsapp_phone = whatsapp_phone
            user.username = username.strip() if username else user.username
            
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

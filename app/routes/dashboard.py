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
from app.models import db, Restaurant, User, TrialHistory
from datetime import datetime, timezone, timedelta
import qrcode 
from io import BytesIO
from PIL import Image
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import (
    check_feature_access,
    get_plan_limits,
    PLAN_LIMITS,
    AI_TOKEN_LIMITS,
    get_subscription_status
)
import re
import unicodedata

import jwt
import logging
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/ai-scan')
@login_required
def ai_scan_redirect():
    """
    Redirige al Scanner IA con un token JWT firmado para autenticación automática.
    Resuelve el problema de sesión compartida entre Flask (puerto 5000) y Scanner IA (puerto 3000).
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or not user.clerk_id:
        flash('Necesitas una cuenta vinculada a Clerk para usar el Scanner IA.', 'warning')
        return redirect(url_for('dashboard.index'))
    
    scanner_url = current_app.config.get('SCANNER_IA_URL', 'http://localhost:3000')
    
    # Generar token JWT con datos del usuario (expira en 5 minutos)
    token_payload = {
        'clerk_id': user.clerk_id,
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=5),
        'iat': datetime.now(timezone.utc)
    }
    
    signed_token = jwt.encode(
        token_payload,
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )
    
    # Redirigir a una página intermedia que envía el token por POST
    return render_template('dashboard/ai_scan_redirect.html',
        scanner_url=scanner_url,
        flask_token=signed_token)

@dashboard_bp.route('/')
@login_required
@active_required
def index():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    menu_url = url_for('public.menu', slug=restaurant.slug, _external=True)
    stats = DashboardService.get_today_overview(restaurant.id)
     
    return render_template('dashboard/index.html', 
                         restaurant=restaurant,
                         pending_count=stats['pending'],
                         confirmed_count=stats['confirmed'],
                         delivered_count=stats['delivered'],
                         total_sales=f"{stats['today_sales_cop']:,}",
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
    
    is_open = DashboardService.toggle_status(restaurant, new_status)
    return jsonify({'success': True, 'is_open': is_open})

@dashboard_bp.route('/api/check-orders')
@login_required
@active_required
def api_check_orders():
    """
    Endpoint ligero para el polling de nuevos pedidos (JS polling cada 15s).
    Devuelve: { new_orders: bool, last_id: int, pending_count: int }
    """
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'not found'}), 404

    data = DashboardService.get_order_polling(restaurant.id)
    return jsonify({
        'last_id': data['last_id'],
        'pending_count': data['pending_count'],
        'new_orders': data['pending_count'] > 0
    })

@dashboard_bp.route('/api/stats')
@login_required
@active_required
def api_stats():
    """Endpoint para obtener estadísticas filtradas por rango (hoy/mes)."""
    restaurant = get_current_restaurant()
    if not restaurant: return jsonify({'error': 'not found'}), 404

    range_type = request.args.get('range', 'today')
    data = DashboardService.get_extended_stats(restaurant.id, range_type)

    return jsonify({
        'success': True,
        'total_sales': data['total_sales_cop'],
        'range': range_type
    })

@dashboard_bp.route('/api/ai-stats')
@login_required
@active_required
def api_ai_stats():
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not user.clerk_id:
        return jsonify({'totalExpenses': 0, 'success': True})

    range_type = request.args.get('range', 'today')
    now = datetime.now(timezone.utc)

    if range_type == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        if now.month == 1:
            start_date = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        query = db.text("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM velzia_expense
            WHERE userId = :clerk_id AND date >= :start_date
        """)

        result = db.session.execute(query, {'clerk_id': user.clerk_id, 'start_date': start_date})
        row = result.fetchone()
        total_expenses = int(row[0]) if row else 0
    except Exception:
        total_expenses = 0

    logger.info(f"api_ai_stats: user={user.id}, clerk_id={user.clerk_id}, range={range_type}, expenses={total_expenses}")

    return jsonify({
        'totalExpenses': total_expenses,
        'success': True
    })

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
    plan_info['ai_tokens'] = AI_TOKEN_LIMITS.get(restaurant.plan_type, 0)
    
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
            if restaurant_name != restaurant.name:
                existing_restaurant = Restaurant.query.filter(
                    Restaurant.name == restaurant_name, 
                    Restaurant.id != restaurant.id
                ).first()
                if existing_restaurant:
                    flash('No se pudieron guardar los cambios. Verifica los datos e intenta de nuevo.', 'error')
                    return render_template('dashboard/profile_form.html', restaurant=restaurant, user=user)

            if whatsapp_phone != restaurant.whatsapp_phone:
                phone_in_trial = TrialHistory.query.filter(
                    TrialHistory.whatsapp_phone == whatsapp_phone
                ).first()
                phone_in_other_restaurant = Restaurant.query.filter(
                    Restaurant.whatsapp_phone == whatsapp_phone,
                    Restaurant.id != restaurant.id,
                    Restaurant.has_used_trial == True
                ).first()
                if phone_in_trial or phone_in_other_restaurant:
                    flash('No es posible usar este número. Intenta con otro.', 'error')
                    return render_template('dashboard/profile_form.html', restaurant=restaurant, user=user)

            restaurant.name = restaurant_name
            restaurant.whatsapp_phone = whatsapp_phone
            user.username = username.strip() if username else user.username
            
            db.session.commit()
            flash('¡Perfil actualizado correctamente!', 'success')
            return redirect(url_for('dashboard.profile'))
        except Exception:
            db.session.rollback()
            flash('No se pudieron guardar los cambios. Verifica los datos e intenta de nuevo.', 'error')
            
    return render_template('dashboard/profile_form.html', 
                         restaurant=restaurant, 
                         user=user)

@dashboard_bp.route('/change-email', methods=['GET', 'POST'])
@login_required
@active_required
def change_email():
    user = User.query.get(session['user_id'])
    is_clerk_user = bool(user.clerk_id)
    
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            new_email = data.get('new_email', '').strip().lower()
            confirm_email = data.get('confirm_email', '').strip().lower()
            current_password = data.get('current_password')
        else:
            new_email = request.form.get('new_email', '').strip().lower()
            confirm_email = request.form.get('confirm_email', '').strip().lower()
            current_password = request.form.get('current_password')

        # Validaciones
        if not new_email or not confirm_email:
            msg = 'Todos los campos son requeridos.'
            if request.is_json:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('dashboard.change_email'))

        if new_email != confirm_email:
            msg = 'Los correos nuevos no coinciden.'
            if request.is_json:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('dashboard.change_email'))

        if '@' not in new_email:
            msg = 'Ingresa un correo valido.'
            if request.is_json:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('dashboard.change_email'))

        # Verificar que el nuevo email no este en uso
        existing_user = User.query.filter(User.email == new_email, User.id != user.id).first()
        if existing_user:
            msg = 'Este correo ya esta registrado por otro usuario.'
            if request.is_json:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('dashboard.change_email'))

        # Verificar contraseña (solo para usuarios no Clerk)
        if not is_clerk_user:
            if not current_password:
                msg = 'Debes ingresar tu contraseña actual.'
                if request.is_json:
                    return jsonify({'success': False, 'message': msg}), 400
                flash(msg, 'error')
                return redirect(url_for('dashboard.change_email'))
            
            if not user.check_password(current_password):
                msg = 'La contraseña actual es incorrecta.'
                if request.is_json:
                    return jsonify({'success': False, 'message': msg}), 400
                flash(msg, 'error')
                return redirect(url_for('dashboard.change_email'))

        # Actualizar email
        try:
            user.email = new_email
            db.session.commit()
            
            msg = '¡Correo actualizado con exito!'
            if request.is_json:
                return jsonify({'success': True, 'message': msg})
            
            flash(msg, 'success')
            return redirect(url_for('dashboard.settings'))
        except Exception as e:
            db.session.rollback()
            msg = 'Error al intentar cambiar el correo. Intenta de nuevo.'
            if request.is_json:
                return jsonify({'success': False, 'message': msg}), 500
            flash(msg, 'error')
            return redirect(url_for('dashboard.change_email'))

    return render_template('dashboard/change_email.html', user=user, is_clerk_user=is_clerk_user)


@dashboard_bp.route('/notifications')
@login_required
@active_required
def notifications():
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)
    return render_template('dashboard/notifications.html', restaurant=restaurant)

from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify
from datetime import datetime, timedelta
from flask_mail import Message
from app import mail, db
from app.forms import LoginForm, ForgotPasswordForm
from app.forms.auth import RegisterEmailForm, RegisterVerifyForm, RegisterSetupForm
from app.models import User, Restaurant
import random
import re
import unicodedata
import mercadopago
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from app.utils.subscription import sanitize_restaurant_limits

auth_bp = Blueprint('auth', __name__)

def send_otp_email(email, otp):
    """Utilidad para enviar el correo de verificación OTP"""
    try:
        msg = Message('Código de Verificación - Velzia',
                      recipients=[email])
        msg.html = render_template('email/otp.html', otp=otp)
        msg.body = f'Tu código de verificación para Velzia es: {otp}' # Fallback text
        mail.send(msg)
        return True
    except Exception as e:
        print(f"ERROR enviando correo: {e}")
        return False


@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['username'] = user.username
            
            # Verificar si el restaurante está activo
            if user.restaurant and not user.restaurant.is_active:
                session['pending_restaurant_id'] = user.restaurant.id
                session['setup_done'] = True # Permitir acceso a la ruta de pago
                flash('Tu suscripción está pendiente de pago.', 'info')
                return redirect(url_for('auth.payment'))
                
            return redirect(url_for('dashboard.index'))
        else:
            flash('Email o contraseña incorrectos')
    return render_template('auth/index.html', form=form)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Generar token seguro (expira en 20 mins)
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = s.dumps(user.email, salt='recover-key')
            
            # Crear URL de recuperación
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Enviar correo
            try:
                msg = Message('Restablecer Contraseña - Velzia', recipients=[user.email])
                msg.html = render_template('email/reset_password.html', reset_url=reset_url)
                msg.body = f'Para restablecer tu contraseña, visita: {reset_url}'
                mail.send(msg)
                flash('Te hemos enviado un correo con las instrucciones.')
            except Exception as e:
                print(f"ERROR MAIL: {e}")
                flash('Hubo un error al enviar el correo. Inténtalo más tarde.')
        else:
            flash('Si el correo está registrado, recibirás un enlace para restablecer tu contraseña.')
        
        # PRG Pattern: Redirigir siempre después de un POST para evitar reenvío
        return redirect(url_for('auth.forgot_password'))
            
    return render_template('auth/forgot_password.html', form=form)

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        # Validar token (max_age=1200 segundos = 20 minutos)
        email = s.loads(token, salt='recover-key', max_age=1200)
    except SignatureExpired:
        flash('El enlace ha expirado. Por favor solicita uno nuevo.')
        return redirect(url_for('auth.forgot_password'))
    except Exception:
        flash('El enlace no es válido.')
        return redirect(url_for('auth.forgot_password'))
    
    # Si es GET, mostrar formulario
    if request.method == 'GET':
        return render_template('auth/reset_password.html')
    
    # Si es POST, actualizar contraseña
    password = request.form.get('password')
    
    user = User.query.filter_by(email=email).first()
    if user and password:
        user.set_password(password)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'redirect': url_for('auth.login'), 'message': '¡Contraseña actualizada! Redirigiendo...'})

        flash('¡Contraseña actualizada! Ya puedes iniciar sesión.')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html')

@auth_bp.route('/privacy')
def privacy():
    return render_template('auth/privacy.html')

@auth_bp.route('/terms')
def terms():
    return render_template('auth/terms.html')

@auth_bp.route('/planes')
def plans():
    return render_template('auth/plans.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Capturar plan si viene de la página de planes
    plan = request.args.get('plan')
    if plan:
        session['selected_plan'] = plan

    from app.forms.auth import RegisterEmailForm
    form = RegisterEmailForm()
    if form.validate_on_submit():
        email = form.email.data
        # Generar código OTP (6 dígitos)
        import random
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        session['otp'] = otp
        session['register_email'] = email
        
        # Enviar correo real vía Gmail
        if send_otp_email(email, otp):
            print(f"DEBUG: OTP enviado a {email}: {otp}")
            flash(f'Hemos enviado un código de verificación a {email}.')
        else:
            flash('Error al enviar el correo de verificación. Por favor intente más tarde.')

        return redirect(url_for('auth.verify_otp'))
    return render_template('auth/register_verify.html', form=form, step='email')

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    from app.forms.auth import RegisterVerifyForm
    if 'register_email' not in session or 'otp' not in session:
        return redirect(url_for('auth.register'))
    
    form = RegisterVerifyForm()
    if form.validate_on_submit():
        # Limpiar y normalizar códigos
        submitted_code = str(form.code.data).strip()
        session_code = str(session.get('otp')).strip()
        
        if submitted_code == session_code:
            session['otp_verified'] = True
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'redirect': url_for('auth.setup_account')})
                
            return redirect(url_for('auth.setup_account'))
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Código incorrecto. Inténtalo de nuevo.'})
                
            flash('Código incorrecto. Inténtalo de nuevo.')
    return render_template('auth/register_verify.html', form=form, step='otp')

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('register_email')
    if not email:
        return jsonify({'success': False, 'message': 'Sesión expirada. Por favor regístrate de nuevo.'})
    
    # Generar nuevo OTP
    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    session['otp'] = otp
    
    if send_otp_email(email, otp):
        return jsonify({'success': True, 'message': f'Hemos enviado un nuevo código a {email}.'})
    else:
        return jsonify({'success': False, 'message': 'No pudimos enviar el código. Inténtalo de nuevo.'})


@auth_bp.route('/setup-account', methods=['GET', 'POST'])
def setup_account():
    if not session.get('otp_verified'):
        return redirect(url_for('auth.register'))
    
    form = RegisterSetupForm()
    email = session.get('register_email')

    if form.validate_on_submit():
        # Validar si el usuario ya existe
        if User.query.filter_by(email=email).first():
            flash('Este correo ya está registrado.')
            return redirect(url_for('auth.login'))

        # Crear Restaurante (Inactivo hasta el pago)
        restaurant_name = form.restaurant_name.data
        # Generar slug simple
        slug = unicodedata.normalize('NFKD', restaurant_name).encode('ascii', 'ignore').decode('ascii')
        slug = re.sub(r'[^\w\s-]', '', slug).strip().lower()
        slug = re.sub(r'[-\s]+', '-', slug)
        
        # Asegurar slug único
        base_slug = slug
        counter = 1
        while Restaurant.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        new_restaurant = Restaurant(
            name=restaurant_name,
            slug=slug,
            whatsapp_phone=form.phone.data,
            plan_type=session.get('selected_plan', 'emprendedor'),
            is_active=False,  # Inactivo hasta el pago
            subscription_expires_at=None  # ← EXPLÍCITO: Sin suscripción hasta pagar
        )
        db.session.add(new_restaurant)
        db.session.flush() # Para obtener el ID

        # Crear Usuario Administrador
        new_user = User(
            username=form.admin_name.data,
            email=email,
            restaurant_id=new_restaurant.id
        )
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        
        try:
            db.session.commit()
            session['pending_restaurant_id'] = new_restaurant.id
            session['setup_done'] = True
            return redirect(url_for('auth.payment'))
        except Exception as e:
            db.session.rollback()
            flash('Error al crear la cuenta. Inténtalo de nuevo.')
            print(f"Error en setup_account: {e}")

    return render_template('auth/register_setup.html', form=form)

@auth_bp.route('/renew', methods=['GET'])
def renew():
    """
    Ruta de renovación para usuarios ya autenticados.
    Permite ir directo al pago sin pasar por registro y verificación.
    """
    # Verificar que el usuario esté autenticado
    if 'user_id' not in session:
        flash('Debes iniciar sesión para renovar tu suscripción.')
        return redirect(url_for('auth.login'))
    
    # Obtener el usuario y su restaurante
    user = User.query.get(session['user_id'])
    if not user or not user.restaurant:
        flash('No se encontró información de tu cuenta.')
        return redirect(url_for('dashboard.index'))
    
    restaurant = user.restaurant
    
    # Capturar plan si viene como parámetro (para cambio de plan)
    plan = request.args.get('plan')
    if plan and plan in ['emprendedor', 'crecimiento', 'elite']:
        # IMPORTANTE: Solo guardar en sesión, NO actualizar en DB hasta que se complete el pago
        session['selected_plan'] = plan
        session['pending_plan_change'] = plan  # Flag para indicar cambio de plan pendiente
    else:
        # Usar el plan actual del restaurante (renovación sin cambio)
        session['selected_plan'] = restaurant.plan_type
        session['pending_plan_change'] = None
    
    # Configurar sesión para el flujo de pago
    session['pending_restaurant_id'] = restaurant.id
    session['setup_done'] = True
    session['is_renewal'] = True  # Flag para identificar que es renovación
    
    return redirect(url_for('auth.payment'))

@auth_bp.route('/payment', methods=['GET', 'POST'])
def payment():
    if not session.get('setup_done'):
        return redirect(url_for('auth.register'))
    
    restaurant_id = session.get('pending_restaurant_id')
    restaurant = Restaurant.query.get(restaurant_id)
    
    if not restaurant:
        return redirect(url_for('auth.register'))

    # Datos dinámicos del plan
    plans_data = {
        'emprendedor': {'name': 'Plan Emprendedor', 'price': '30.000'},
        'crecimiento': {'name': 'Plan Crecimiento', 'price': '40.000'},
        'elite': {'name': 'Plan Élite', 'price': '50.000'}
    }
    
    selected_plan_key = session.get('selected_plan', 'crecimiento')
    plan_info = plans_data.get(selected_plan_key, plans_data['crecimiento'])

    # Integración con Mercado Pago
    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    
    # Limpiar precio para MP (debe ser float/int)
    price_val = float(plan_info['price'].replace('.', ''))

    preference_data = {
        "items": [
            {
                "title": f"Suscripción Velzia - {plan_info['name']}",
                "quantity": 1,
                "unit_price": price_val,
                "currency_id": "COP"
            }
        ],
        "back_urls": {
            "success": "https://changelessly-polygonaceous-emmalee.ngrok-free.dev/payment-callback",
            "failure": "https://changelessly-polygonaceous-emmalee.ngrok-free.dev/payment",
            "pending": "https://changelessly-polygonaceous-emmalee.ngrok-free.dev/payment-callback"
        },
        "auto_return": "approved",
        "external_reference": f"{restaurant_id}:{selected_plan_key}",
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "ticket"} # Opcional: excluir efectivo para activación inmediata
            ],
            "installments": 1
        }
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        
        # Debug response
        if "init_point" not in preference:
            print(f"MP ERROR RAW: {preference_response}")
        
        checkout_url = preference["init_point"]
    except Exception as e:
        print(f"Error creando preferencia MP: {e}")
        # Si hay una respuesta previa con error, intentalo imprimir
        try:
             print(f"MP DETAILED ERROR: {preference_response}")
        except:
             pass
        checkout_url = "#"
        flash("Error al conectar con la pasarela de pago. Inténtalo de nuevo.")

    return render_template('auth/payment.html', restaurant=restaurant, plan_info=plan_info, checkout_url=checkout_url)

@auth_bp.route('/payment-callback')
def payment_callback():
    status = request.args.get('status')
    restaurant_id = request.args.get('external_reference')
    
    if status in ['approved', 'pending']:
        restaurant = Restaurant.query.get(restaurant_id)
        if restaurant:
            # Activar restaurante
            restaurant.is_active = True
            
            # Extender suscripción
            # Si ya tiene fecha de expiración y aún no ha expirado, extender desde esa fecha
            # Si no tiene o ya expiró, extender desde ahora
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            if restaurant.subscription_expires_at:
                expires_at = restaurant.subscription_expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                
                if expires_at > now_utc:
                    # Renovación: extender desde la fecha actual de expiración
                    restaurant.subscription_expires_at = expires_at + timedelta(days=30)
                else:
                    # Expirada: establecer desde ahora
                    restaurant.subscription_expires_at = now_utc + timedelta(days=30)
            else:
                # Nueva suscripción: establecer desde ahora
                restaurant.subscription_expires_at = now_utc + timedelta(days=30)
            
            db.session.commit()
            
            # Verificar si es renovación
            is_renewal = session.get('is_renewal', False)
            
            # Aplicar cambio de plan desde external_reference (más confiable que la sesión)
            try:
                if ':' in external_reference:
                    _, plan_type = external_reference.split(':', 1)
                    if plan_type in ['emprendedor', 'crecimiento', 'elite']:
                        restaurant.plan_type = plan_type
            except Exception as e:
                print(f"Error parsing plan from external_reference: {e}")
            
            # Respaldo: Aplicar cambio de plan desde sesión si existe
            pending_plan = session.get('pending_plan_change')
            if pending_plan and pending_plan in ['emprendedor', 'crecimiento', 'elite']:
                restaurant.plan_type = pending_plan
            
            db.session.commit()

            # Aplicar límites del nuevo plan inmediatamente
            try:
                sanitize_restaurant_limits(restaurant)
            except Exception as e:
                print(f"Error sanitizing limits in callback: {e}")
            
            # Limpiar sesión de registro/renovación
            session.pop('otp', None)
            session.pop('register_email', None)
            session.pop('otp_verified', None)
            session.pop('setup_done', None)
            session.pop('pending_restaurant_id', None)
            session.pop('selected_plan', None)
            session.pop('is_renewal', None)
            session.pop('pending_plan_change', None)
            
            if status == 'approved':
                if is_renewal:
                    flash('¡Pago exitoso! Tu suscripción ha sido renovada.')
                    return redirect(url_for('dashboard.subscription'))
                else:
                    flash('¡Pago exitoso! Tu cuenta ha sido activada.')
                    return redirect(url_for('auth.login'))
            else:
                flash('Tu pago está pendiente de aprobación. Hemos activado tu acceso temporalmente.')
                if is_renewal:
                    return redirect(url_for('dashboard.subscription'))
                else:
                    return redirect(url_for('auth.login'))
    
    flash('No pudimos confirmar tu pago. Regresa e inténtalo de nuevo.')
    return redirect(url_for('auth.payment'))

@auth_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Recibe notificaciones de Mercado Pago sobre actualizaciones de pago.
    """
    try:
        data = request.get_json()
        print(f"WEBHOOK RECEIVED: {data}")
        
        if not data:
             # Mercado Pago sometimes sends data in form-data or other ways, but usually JSON
             # If data is None, try request.args for 'topic' and 'id'
             pass

        # Validar tipo de notificación (nos interesa 'payment')
        # MP puede enviar notification type 'payment' o 'topic' -> 'payment' en query params
        payment_id = None
        
        # Caso 1: JSON body
        if data and data.get("type") == "payment":
             payment_id = data.get("data", {}).get("id")
        
        # Caso 2: Query params (topic=payment&id=123)
        if not payment_id:
            topic = request.args.get('topic') or request.args.get('type')
            if topic == 'payment':
                payment_id = request.args.get('id') or request.args.get('data.id')

        if payment_id:
            # Consultar estado del pago directamente a la API de MP
            sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get("response")
            
            if payment and payment.get("status") == "approved":
                external_ref = payment.get("external_reference")
                if external_ref:
                    restaurant_id = int(external_ref)
                    print(f"WEBHOOK: Activating restaurant {restaurant_id} for payment {payment_id}")
                    
                    # Activar restaurante
                    restaurant = Restaurant.query.get(restaurant_id)
                    if restaurant:
                        restaurant.is_active = True
                        
                        # Actualizar plan desde external_reference
                        try:
                            if ':' in external_ref:
                                _, plan_type = external_ref.split(':', 1)
                                if plan_type in ['emprendedor', 'crecimiento', 'elite']:
                                    restaurant.plan_type = plan_type
                        except Exception as e:
                            print(f"WEBHOOK: Error parsing plan: {e}")

                        # Extender suscripción (Misma lógica que payment_callback)
                        from datetime import timezone
                        now_utc = datetime.now(timezone.utc)
                        if restaurant.subscription_expires_at:
                            expires_at = restaurant.subscription_expires_at
                            if expires_at.tzinfo is None:
                                expires_at = expires_at.replace(tzinfo=timezone.utc)
                            
                            if expires_at > now_utc:
                                # Renovación: extender desde la fecha actual de expiración
                                restaurant.subscription_expires_at = expires_at + timedelta(days=30)
                            else:
                                # Expirada: establecer desde ahora
                                restaurant.subscription_expires_at = now_utc + timedelta(days=30)
                        else:
                            # Nueva suscripción: establecer desde ahora
                            restaurant.subscription_expires_at = now_utc + timedelta(days=30)

                        db.session.commit()

                        # Aplicar límites del nuevo plan inmediatamente
                        try:
                            sanitize_restaurant_limits(restaurant)
                        except Exception as e:
                            print(f"Error sanitizing limits in webhook: {e}")

                        return "OK", 200
        
        return "OK", 200  
    except Exception as e:
        print(f"WEBHOOK ERROR: {e}")
        return "ERROR", 500

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.')
    return redirect(url_for('auth.login'))

        

from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify
from datetime import datetime, timedelta, timezone
from flask_mail import Message
from app import mail, db
from app.forms import LoginForm, ForgotPasswordForm
from app.forms.auth import RegisterEmailForm, RegisterVerifyForm, RegisterSetupForm
from app.models import User, Restaurant, TrialHistory
import random
import secrets
import re
import unicodedata
import mercadopago
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.utils.subscription import sanitize_restaurant_limits

auth_bp = Blueprint('auth', __name__)

from app import csrf  # para eximir el webhook de CSRF
def send_otp_email(email, otp):
    try:
        msg = Message('Código de Verificación - Velzia',
                      recipients=[email])
        msg.html = render_template('email/otp.html', otp=otp)
        msg.body = f'Tu código de verificación para Velzia es: {otp}'
        mail.send(msg)
        return True
    except Exception as e:
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
            
            if user.restaurant and not user.restaurant.is_active:
                session['pending_restaurant_id'] = user.restaurant.id
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
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            try:
                msg = Message('Restablecer Contraseña - Velzia', recipients=[user.email])
                msg.html = render_template('email/reset_password.html', reset_url=reset_url)
                msg.body = f'Para restablecer tu contraseña, visita: {reset_url}'
                mail.send(msg)
                flash('Te hemos enviado un correo con las instrucciones.', 'success')
                return redirect(url_for('auth.login'))
            except Exception as e:
                flash('Hubo un error al enviar el correo. Inténtalo más tarde.', 'error')
        else:
            flash('Si el correo está registrado, recibirás un enlace para restablecer tu contraseña.', 'info')
        
        # PRG Pattern: Redirigir siempre después de un POST para evitar reenvío
        return redirect(url_for('auth.forgot_password'))
            
    return render_template('auth/forgot_password.html', form=form)

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='recover-key', max_age=3600)
    except SignatureExpired:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'El enlace ha expirado. Por favor solicita uno nuevo.'})
        flash('El enlace ha expirado. Por favor solicita uno nuevo.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'El enlace no es válido.'})
        flash('El enlace no es válido.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except Exception as e:
        print(f"Error en reset_password: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Ocurrió un error inesperado.'})
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'GET':
        return render_template('auth/reset_password.html')
    
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if password != confirm_password:
        msg = 'Las contraseñas no coinciden.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': msg})
        flash(msg, 'error')
        return render_template('auth/reset_password.html')

    # Validaciones de complejidad adicionales
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        msg = 'La contraseña no cumple con los requisitos de seguridad (mín. 8 caracteres, una mayúscula y un número).'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': msg})
        flash(msg, 'error')
        return render_template('auth/reset_password.html')

    user = User.query.filter_by(email=email).first()
    if user and password:
        user.set_password(password)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True, 
                'redirect': url_for('auth.login'), 
                'message': '¡Contraseña actualizada exitosamente! Redirigiendo...'
            })

        flash('¡Contraseña actualizada! Ya puedes iniciar sesión.')
        return redirect(url_for('auth.login'))
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'message': 'No se pudo actualizar la contraseña.'})
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
    plan = request.args.get('plan')
    if plan:
        session['selected_plan'] = plan

    from app.forms.auth import RegisterEmailForm
    form = RegisterEmailForm()
    if form.validate_on_submit():
        email = form.email.data

        # Limpiar SIEMPRE la sesión anterior al iniciar un nuevo intento de registro.
        # Esto previene el exploit de sesión cacheada: si un intento previo dejó un
        # OTP válido en sesión, el siguiente submit lo borra obligatoriamente.
        session.pop('otp', None)
        session.pop('register_email', None)
        session.pop('otp_verified', None)

        user_exists = User.query.filter_by(email=email).first()
        
        if user_exists:
            try:
                msg = Message('Ya eres parte de Velzia', recipients=[email])
                login_url = url_for('auth.login', _external=True)
                msg.html = render_template('email/account_exists.html', login_url=login_url)
                msg.body = f"Ya tienes una cuenta activa en Velzia. Puedes iniciar sesión aquí: {login_url}"
                mail.send(msg)
            except Exception as e:
                 print(f"Error enviando correo de cuenta existente: {e}")
        else:
            # Verificar abuso de trial ANTES de enviar el OTP
            selected_plan = session.get('selected_plan', 'emprendedor')
            if selected_plan == 'trial':
                past_trial = TrialHistory.query.filter_by(email=email).first()
                if past_trial:
                    flash('Este correo ya disfrutó de una prueba gratuita. Por favor elige un plan pago para continuar.', 'warning')
                    return render_template('auth/register_verify.html', form=form, step='email')

            import random
            otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            session['otp'] = otp
            session['register_email'] = email
            
            if not send_otp_email(email, otp):
                flash('Error al enviar el correo de verificación. Por favor intente más tarde.')
                return render_template('auth/register_verify.html', form=form, step='email')

        # Respuesta UNIFICADA: Independientemente de si existe o no
        flash('Si el correo ingresado es correcto, recibirás instrucciones para continuar.')
        return redirect(url_for('auth.verify_otp'))
    return render_template('auth/register_verify.html', form=form, step='email')

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    from app.forms.auth import RegisterVerifyForm
    if 'register_email' not in session or 'otp' not in session:
        return redirect(url_for('auth.register'))
    
    form = RegisterVerifyForm()
    if form.validate_on_submit():
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
        if User.query.filter_by(email=email).first():
            return redirect(url_for('auth.login'))

        # Validar abuso de Trial por Teléfono y Email (Tenant Check)
        past_active_trial = Restaurant.query.filter_by(whatsapp_phone=form.phone.data, has_used_trial=True).first()
        past_history_trial = TrialHistory.query.filter(
            db.or_(TrialHistory.email == email, TrialHistory.whatsapp_phone == form.phone.data)
        ).first()
        
        selected_plan = session.get('selected_plan', 'emprendedor')
        is_trial = selected_plan == 'trial'

        if is_trial and (past_active_trial or past_history_trial):
            flash('Este correo o número ya disfrutó de una prueba gratuita. Por favor elige un plan pago para tu nueva sucursal.', 'warning')
            return render_template('auth/register_setup.html', form=form, plan=selected_plan)

        restaurant_name = form.restaurant_name.data
        slug = unicodedata.normalize('NFKD', restaurant_name).encode('ascii', 'ignore').decode('ascii')
        slug = re.sub(r'[^\w\s-]', '', slug).strip().lower()
        slug = re.sub(r'[-\s]+', '-', slug)
        
        base_slug = slug
        counter = 1
        while Restaurant.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        selected_plan = session.get('selected_plan', 'emprendedor')
        is_trial = selected_plan == 'trial'
        
        if is_trial:
            trial_expires_at = datetime.now(timezone.utc) + timedelta(days=10)
            is_active_val = True
            expires_at_val = trial_expires_at
            plan_type_val = 'trial'
            has_used_trial_val = False
        else:
            is_active_val = False
            expires_at_val = None
            plan_type_val = selected_plan
            has_used_trial_val = False

        new_restaurant = Restaurant(
            name=restaurant_name,
            slug=slug,
            whatsapp_phone=form.phone.data,
            plan_type=plan_type_val,
            is_active=is_active_val,
            subscription_expires_at=expires_at_val,
            is_open=True,
            has_used_trial=has_used_trial_val
        )
        db.session.add(new_restaurant)
        db.session.flush()

        new_user = User(
            username=form.admin_name.data.strip() if form.admin_name.data else "",
            email=email,
            restaurant_id=new_restaurant.id
        )
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        
        if is_trial:
            new_history_record = TrialHistory(email=email, whatsapp_phone=form.phone.data)
            db.session.add(new_history_record)

        
        try:
            db.session.commit()
            
            if is_trial:
                # Caso TRIAL: Auto-login y Dashboard
                session['user_id'] = new_user.id
                session['username'] = new_user.username
                
                
                

                
                flash('¡Registro exitoso! Disfruta de tus 10 días de prueba gratuita.', 'success')
                return redirect(url_for('dashboard.index'))
            else:
                # Caso PAGO: Redirigir a payment
                session['pending_restaurant_id'] = new_restaurant.id
                return redirect(url_for('auth.payment'))

        except Exception as e:
            db.session.rollback()
            flash('Error al crear la cuenta. Inténtalo de nuevo.')
            print(f"Error en setup_account: {e}")

    return render_template('auth/register_setup.html', form=form, plan=session.get('selected_plan'))

@auth_bp.route('/renew', methods=['GET'])
def renew():
    """
    Ruta de renovación para usuarios ya autenticados.
    Permite ir directo al pago sin pasar por registro y verificación.
    """
    if 'user_id' not in session:
        flash('Debes iniciar sesión para renovar tu suscripción.')
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    if not user or not user.restaurant:
        flash('No se encontró información de tu cuenta.')
        return redirect(url_for('dashboard.index'))
    
    restaurant = user.restaurant
    
    plan = request.args.get('plan')
    if plan and plan in ['emprendedor', 'crecimiento', 'elite']:
        session['selected_plan'] = plan
        session['pending_plan_change'] = plan
    else:
        session['selected_plan'] = restaurant.plan_type
        session['pending_plan_change'] = None
    
    session['pending_restaurant_id'] = restaurant.id
    session['is_renewal'] = True
    
    return redirect(url_for('auth.payment'))

@auth_bp.route('/payment', methods=['GET', 'POST'])
def payment():
    restaurant_id = session.get('pending_restaurant_id')
    
    # Si no hay un ID pendiente pero el usuario está logueado, usar su restaurante actual (Upgrade)
    if not restaurant_id and 'user_id' in session:
        from app.utils.restaurant import get_current_restaurant
        current_res = get_current_restaurant()
        if current_res:
            restaurant_id = current_res.id
            session['pending_restaurant_id'] = restaurant_id
    
    if not restaurant_id:
        return redirect(url_for('auth.register'))
    
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

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    price_val = float(plan_info['price'].replace('.', ''))

    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    
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
            "success": f"{base_url}/payment-callback",
            "failure": f"{base_url}/payment",
            "pending": f"{base_url}/payment-callback"
        },
        "auto_return": "approved",
        "external_reference": f"{restaurant_id}:{selected_plan_key}",
        "notification_url": f"{base_url}/webhook",
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
            if status == 'approved':
                restaurant.is_active = True
                db.session.commit()
            
            is_renewal = session.get('is_renewal', False)

            sanitize_restaurant_limits(restaurant)
            
            session.pop('otp', None)
            session.pop('register_email', None)
            session.pop('otp_verified', None)
            session.pop('pending_restaurant_id', None)
            session.pop('selected_plan', None)
            session.pop('is_renewal', None)
            session.pop('pending_plan_change', None)
            
            if status == 'approved':
                if is_renewal:
                    return redirect(url_for('dashboard.subscription'))
                else:
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
@csrf.exempt  # MP es servicio externo — no puede enviar token CSRF
def webhook():
    """
    Recibe notificaciones de Mercado Pago sobre actualizaciones de pago.
    """
    try:
        data = request.get_json()

        
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
                    # Parsear restaurant_id y plan desde external_reference (formato: "id:plan")
                    try:
                        if ':' in external_ref:
                            restaurant_id_str, plan_type = external_ref.split(':', 1)
                            restaurant_id = int(restaurant_id_str)
                        else:
                            restaurant_id = int(external_ref)
                            plan_type = None
                    except (ValueError, TypeError):
                        return "OK", 200

                    # Log minimal para producción (sin datos sensibles)
                    current_app.logger.info(f"WEBHOOK: Activating restaurant {restaurant_id}")
                    
                    # Activar restaurante
                    restaurant = Restaurant.query.get(restaurant_id)
                    if restaurant:
                        restaurant.is_active = True
                        
                        # Actualizar plan desde external_reference
                        if plan_type and plan_type in ['emprendedor', 'crecimiento', 'elite']:
                            restaurant.plan_type = plan_type

                        # Extender suscripción (Solo Webhook + Protección Anti-Duplicados)
                        from datetime import timezone
                        now_utc = datetime.now(timezone.utc)
                        
                        expires_at = restaurant.subscription_expires_at
                        if expires_at and expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)

                        # PROTECCIÓN: Si la suscripción expira en más de 35 días, ignoramos el webhook (Bounce de MP)
                        if expires_at and (expires_at - now_utc).days > 35:
                            pass
                        else:
                            if expires_at and expires_at > now_utc:
                                restaurant.subscription_expires_at = expires_at + timedelta(days=30)
                            else:
                                restaurant.subscription_expires_at = now_utc + timedelta(days=30)

                            db.session.commit()

                        # Aplicar límites del nuevo plan inmediatamente
                        try:
                            sanitize_restaurant_limits(restaurant)
                        except Exception as e:
                            pass

                        return "OK", 200
        
        return "OK", 200  
    except Exception as e:
        # print(f"WEBHOOK ERROR: {e}")
        return "ERROR", 500


@auth_bp.route('/api/sync-clerk', methods=['POST'])
def sync_clerk():
    """Sincroniza el usuario de Clerk con la base de datos local"""
    from app.utils.auth import verify_clerk_session

    # Verificación de seguridad: Clerk maneja la autenticación.
    # En un entorno de producción, aquí verificaríamos el JWT de Clerk.
    # Por ahora, confiamos en la sincronización del frontend si el token es válido.

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    email = data.get('email')
    username = data.get('username') or (email.split('@')[0] if email else 'User')

    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400

    user = User.query.filter_by(email=email).first()

    is_new_user = False
    if not user:
        user = User(email=email, username=username)
        user.set_password(secrets.token_hex(16))
        db.session.add(user)
        db.session.commit()
        is_new_user = True

    session['user_id'] = user.id
    session['username'] = user.username

    redirect_url = url_for('dashboard.index') if user.restaurant_id else url_for('auth.plans')

    return jsonify({
        'success': True,
        'has_restaurant': user.restaurant_id is not None,
        'is_new_user': is_new_user,
        'redirect': redirect_url
    })

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.')
    return redirect(url_for('auth.login'))

        

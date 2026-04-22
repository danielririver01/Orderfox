from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify
from datetime import datetime, timedelta, timezone
from flask_mail import Message
from app import mail, db
from app.forms import LoginForm, ForgotPasswordForm
from app.forms.auth import RegisterEmailForm, RegisterVerifyForm, RegisterSetupForm
from app.models import User, Restaurant, TrialHistory
import random
import re
import unicodedata
import mercadopago
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.utils.subscription import sanitize_restaurant_limits, initialize_or_reset_token_wallet

auth_bp = Blueprint('auth', __name__)

from app.extensions import csrf

@auth_bp.route('/api/sync-clerk', methods=['POST'])
@csrf.exempt
def sync_clerk():
    """
    Sincroniza el usuario de Clerk con la base de datos local.
    Realiza una verificación segura consultando la API de Clerk.
    """
    data = request.get_json()
    clerk_id = data.get('clerk_id')
    email = data.get('email')
    session_id = data.get('session_id')
    
    # 1. Verificación en el backend contra Clerk
    clerk_secret = current_app.config.get('CLERK_SECRET_KEY')
    if not clerk_secret:
        return jsonify({'success': False, 'message': 'Clerk secret not configured'}), 500
        
    try:
        import requests
        # Verificar la sesión activa primero
        session_resp = requests.get(
            f"https://api.clerk.com/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {clerk_secret}"},
            timeout=5
        )
        
        if session_resp.status_code != 200 or session_resp.json().get('status') != 'active':
             return jsonify({'success': False, 'message': 'Invalid or inactive session'}), 401
             
        # Verificar los datos del usuario
        response = requests.get(
            f"https://api.clerk.com/v1/users/{clerk_id}",
            headers={"Authorization": f"Bearer {clerk_secret}"},
            timeout=5
        )
        
        if response.status_code != 200:
             return jsonify({'success': False, 'message': 'Invalid Clerk user'}), 401
             
        clerk_user_data = response.json()
        
        # Buscar el email primario por ID
        verified_email = next(
            (e['email_address'] for e in clerk_user_data.get('email_addresses', []) 
             if e['id'] == clerk_user_data.get('primary_email_address_id')), 
            None
        )
        
        # Fallback: para usuarios OAuth (Google/Facebook) buscar el email en toda la lista
        if not verified_email:
            all_emails = [e['email_address'] for e in clerk_user_data.get('email_addresses', [])]
            if email.lower() in [e.lower() for e in all_emails]:
                verified_email = email  # El email existe y viene del JWT de Clerk
        
        # Seguridad: Comparar el email del cliente con el verificado por Clerk (case-insensitive)
        if not verified_email or verified_email.lower() != email.lower():
             return jsonify({'success': False, 'message': 'Email mismatch or not verified'}), 401
        
        # Normalizar email al verificado por Clerk
        email = verified_email
             
    except Exception as e:
        current_app.logger.error(f"Error verifying Clerk user: {e}")
        return jsonify({'success': False, 'message': 'Verification failed'}), 500

    username = data.get('username') or email.split('@')[0]

    if not email or not clerk_id:
        return jsonify({'success': False, 'message': 'Identification is required'}), 400

    user = User.query.filter_by(email=email).first()

    if not user:
        # Si el usuario no existe, lo creamos
        user = User(
            email=email,
            username=username,
            password='clerk_authenticated',  # Password dummy
            clerk_id=clerk_id
        )
        db.session.add(user)
        db.session.commit()
    else:
        # Actualizar clerk_id si no estaba guardado (usuarios anteriores a v2.0.0)
        if not user.clerk_id:
            user.clerk_id = clerk_id
            db.session.commit()

    # Inicializar wallet de tokens si no existe (Velzia 2.0.0 Alpha)
    if not user.token_wallet:
        initialize_or_reset_token_wallet(user)

    session['user_id'] = user.id
    session['username'] = user.username
    session['clerk_id'] = clerk_id

    # Redirección lógica: si es nuevo y no tiene restaurante, ir a configuración de cuenta
    redirect_url = url_for('dashboard.index')
    if not user.restaurant:
        # Si viene de registro silencioso, mandarlo a configurar su restaurante
        redirect_url = url_for('auth.setup_account')

    return jsonify({
        'success': True,
        'redirect_url': redirect_url
    })

@auth_bp.route('/api/sync-clerk-redirect')
def sync_clerk_redirect():
    return render_template('auth/sync_clerk.html')

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

@auth_bp.route('/register', methods=['GET'])
def register():
    plan = request.args.get('plan')
    if plan:
        session['selected_plan'] = plan
    
    # Renderizamos la página de registro (ahora manejada por Clerk SignUp en el cliente)
    return render_template('auth/register_verify.html', step='email')

# Rutas de OTP legadas eliminadas - Velzia 2.0.0 usa Clerk para identidad gestionada


@auth_bp.route('/setup-account', methods=['GET', 'POST'])
def setup_account():
    # El usuario debe estar autenticado (vía Clerk o tradicional)
    if 'user_id' not in session:
        return redirect(url_for('auth.register'))
    
    from app.forms.auth import RegisterSetupForm
    form = RegisterSetupForm()
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('auth.register'))
        
    # Si ya tiene restaurante, no debería estar aquí
    if user.restaurant:
        return redirect(url_for('dashboard.index'))

    email = user.email

    # Si es usuario de Clerk, relajamos la validación de campos que ya no necesitamos
    if user.clerk_id:
        form.admin_name.validators = []
        form.password.validators = []
        form.confirm_password.validators = []

    if form.validate_on_submit():

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

        # Vinculamos al usuario existente con el nuevo restaurante
        user.restaurant_id = new_restaurant.id
        
        # Si NO es Clerk, actualizamos identidad (tradicional)
        if not user.clerk_id:
            user.username = form.admin_name.data.strip()
            user.set_password(form.password.data)
        
        if is_trial:
            new_history_record = TrialHistory(email=email, whatsapp_phone=form.phone.data)
            db.session.add(new_history_record)

        try:
            db.session.commit()
            
            if is_trial:
                # Caso TRIAL: El usuario ya está en la sesión de Flask, actualizamos username
                session['username'] = user.username
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

    return render_template('auth/register_setup.html', form=form, plan=session.get('selected_plan'), user=user)

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
            
            # Reset de tokens IA al activar/renovar plan (Fase 1 Velzia 2.0.0)
            from app.models import User
            user = User.query.filter_by(restaurant_id=restaurant.id).first()
            if user:
                mp_payment_id = request.args.get('payment_id')
                initialize_or_reset_token_wallet(user, is_reset=True, mp_payment_id=mp_payment_id)

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
@csrf.exempt
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
                            # Reset de tokens IA vía Webhook
                            user = User.query.filter_by(restaurant_id=restaurant.id).first()
                            if user:
                                initialize_or_reset_token_wallet(user, is_reset=True, mp_payment_id=payment_id)
                        except Exception as e:
                            pass

                        return "OK", 200
        
        return "OK", 200  
    except Exception as e:
        # print(f"WEBHOOK ERROR: {e}")
        return "ERROR", 500

@auth_bp.route('/logout')
def logout():
    session.clear()
    return render_template('auth/logout_clerk.html')

        

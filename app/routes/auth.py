from flask import Blueprint, render_template, redirect, url_for, flash, session, request
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

auth_bp = Blueprint('auth', __name__)


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
            flash('Se han enviado las instrucciones a tu correo.')
        else:
            flash('No pudimos validar la información ingresada. Revisa tus datos e inténtalo de nuevo')
    return render_template('auth/forgot_password.html', form=form)

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
        try:
            msg = Message('Código de Verificación - Velzia',
                          recipients=[email])
            msg.body = f'Tu código de verificación para Velzia es: {otp}'
            mail.send(msg)
            print(f"DEBUG: OTP enviado a {email}: {otp}")
            flash(f'Hemos enviado un código de verificación a {email}.')
        except Exception as e:
            print(f"ERROR enviando correo: {e}")
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
        if form.code.data == session.get('otp'):
            session['otp_verified'] = True
            return redirect(url_for('auth.setup_account'))
        else:
            flash('Código incorrecto. Inténtalo de nuevo.')
    return render_template('auth/register_verify.html', form=form, step='otp')

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
            is_active=False # Inactivo hasta el pago
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
            "success": url_for('auth.payment_callback', _external=True),
            "failure": url_for('auth.payment', _external=True),
            "pending": url_for('auth.payment_callback', _external=True)
        },
        "auto_return": "approved",
        "external_reference": str(restaurant_id),
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
        checkout_url = preference["init_point"]
    except Exception as e:
        print(f"Error creando preferencia MP: {e}")
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
            restaurant.is_active = True
            db.session.commit()
            
            # Limpiar sesión de registro
            session.pop('otp', None)
            session.pop('register_email', None)
            session.pop('otp_verified', None)
            session.pop('setup_done', None)
            session.pop('pending_restaurant_id', None)
            session.pop('selected_plan', None)
            
            if status == 'approved':
                flash('¡Pago exitoso! Tu cuenta ha sido activada.')
            else:
                flash('Tu pago está pendiente de aprobación. Hemos activado tu acceso temporalmente.')
                
            return redirect(url_for('auth.login'))
    
    flash('No pudimos confirmar tu pago. Regresa e inténtalo de nuevo.')
    return redirect(url_for('auth.payment'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente')
    return redirect(url_for('auth.login'))

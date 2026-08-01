from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, current_app
from app import db
from app.forms import LoginForm
from app.forms.auth import RegisterSetupForm
from app.models import Restaurant
from app.utils.subscription import initialize_or_reset_token_wallet
from app.utils.mp_webhook import extract_mp_signature, verify_mp_signature
from app.services.auth_service import AuthService
from app.services.subscription_service import SubscriptionService
from app.utils.restaurant import get_current_restaurant
import mercadopago

auth_bp = Blueprint('auth', __name__)

from app.csrf import csrf

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

    # 1. Verificación en el backend contra Clerk (delegada al servicio)
    verified_email, error = AuthService.verify_clerk_session(session_id, clerk_id, email)
    if error:
        return jsonify({
            'success': False,
            'message': error.get('message', 'Verification failed'),
            'error_code': error.get('error_code', 'VERIFICATION_FAILED')
        }), 401 if error.get('error_code') in ('INVALID_SESSION', 'INVALID_USER', 'EMAIL_MISMATCH') else 500

    email = verified_email

    username = data.get('username') or email.split('@')[0]

    # 2. Delegar sync / creación de usuario al servicio
    user, is_new, plan_or_error = AuthService.sync_or_create_user(
        clerk_id, email, username
    )

    if user is None:
        return jsonify({
            'success': False,
            'message': plan_or_error.get('message', 'Error de registro'),
            'error_code': plan_or_error.get('error_code', 'REGISTRATION_ERROR')
        }), 500

    session['user_id'] = user.id
    session['username'] = user.username
    session['clerk_id'] = clerk_id

    if is_new:
        session['selected_plan'] = plan_or_error  # plan string
        return jsonify({
            'success': True,
            'message': f'¡Bienvenido! Completa tu registro para activar tu plan {plan_or_error}.',
            'is_new_user': True,
            'redirect_url': url_for('auth.setup_account')
        })

    redirect_url = url_for('dashboard.index')
    if not user.restaurant:
        redirect_url = url_for('auth.setup_account')

    return jsonify({
        'success': True,
        'redirect_url': redirect_url
    })


@auth_bp.route('/api/sync-clerk-redirect')
def sync_clerk_redirect():
    return render_template('auth/sync_clerk.html')


@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user, error = AuthService.authenticate(
            form.email.data, form.password.data
        )
        if user:
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


@auth_bp.route('/privacy')
def privacy():
    return redirect(url_for('auth.legal'))


@auth_bp.route('/terms')
def terms():
    return redirect(url_for('auth.legal'))


@auth_bp.route('/legal')
def legal():
    return render_template('dashboard/legal.html')


@auth_bp.route('/planes')
def plans():
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        if user and not user.restaurant:
            return redirect(url_for('auth.setup_account'))
    return render_template('auth/plans.html')


@auth_bp.route('/register', methods=['GET'])
def register():
    plan = request.args.get('plan')
    if plan:
        session['selected_plan'] = plan

    selected_plan = session.get('selected_plan', 'emprendedor')
    return render_template('auth/register_verify.html', step='email', plan=selected_plan)


@auth_bp.route('/api/save-plan-selection', methods=['POST'])
def save_plan_selection():
    """
    Endpoint que guarda la pre-registración cuando el usuario selecciona un plan.
    """
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    plan = data.get('plan', '').strip()

    if not email or not plan:
        return jsonify({
            'success': False,
            'message': 'Email y plan son requeridos'
        }), 400

    result, error = AuthService.save_plan_selection(email, plan)
    if error:
        return jsonify({
            'success': False,
            'message': error['message']
        }), 400

    return jsonify({
        'success': True,
        'message': f'Plan {plan} guardado. Redirigiendo a login...'
    })


@auth_bp.route('/setup-account', methods=['GET', 'POST'])
def setup_account():
    if 'user_id' not in session:
        return redirect(url_for('auth.register'))

    form = RegisterSetupForm()

    user = AuthService.get_user(session['user_id'])
    if not user:
        return redirect(url_for('auth.register'))

    if user.restaurant:
        return redirect(url_for('dashboard.index'))

    email = user.email

    if user.clerk_id:
        form.admin_name.validators = []
        form.password.validators = []
        form.confirm_password.validators = []

    if form.validate_on_submit():
        selected_plan = session.get('selected_plan', 'emprendedor')
        is_trial = selected_plan == 'trial'

        # Trial eligibility check
        if is_trial:
            blocked, msg = AuthService.check_trial_eligibility(
                email, form.phone.data
            )
            if blocked:
                flash(msg, 'warning')
                return render_template('auth/register_setup.html', form=form,
                                       plan=selected_plan)

        restaurant, error_msg = AuthService.create_restaurant_from_setup(
            user=user,
            email=email,
            restaurant_name=form.restaurant_name.data,
            phone=form.phone.data,
            selected_plan=selected_plan,
            admin_name=form.admin_name.data,
            password=form.password.data,
        )

        if error_msg:
            flash(error_msg)
            return render_template('auth/register_setup.html', form=form,
                                   plan=selected_plan, user=user)

        if is_trial:
            session['username'] = user.username
            return redirect(url_for('dashboard.index'))
        else:
            session['pending_restaurant_id'] = restaurant.id
            return redirect(url_for('auth.payment'))

    return render_template('auth/register_setup.html', form=form,
                           plan=session.get('selected_plan'), user=user)


@auth_bp.route('/renew', methods=['GET'])
def renew():
    """
    Ruta de renovación para usuarios ya autenticados.
    """
    if 'user_id' not in session:
        flash('Debes iniciar sesión para renovar tu suscripción.')
        return redirect(url_for('auth.login'))

    user = AuthService.get_user(session['user_id'])
    if not user or not user.restaurant:
        flash('No se encontró información de tu cuenta.')
        return redirect(url_for('dashboard.index'))

    restaurant = user.restaurant

    plan = request.args.get('plan')
    if plan and plan in ('emprendedor', 'crecimiento', 'elite'):
        session['selected_plan'] = plan
        session['pending_plan_change'] = plan
    else:
        current_plan = restaurant.plan_type
        if current_plan == 'trial':
            flash('Selecciona un plan de pago para continuar.')
            return redirect(url_for('auth.plans'))
        session['selected_plan'] = current_plan
        session['pending_plan_change'] = None

    session['pending_restaurant_id'] = restaurant.id
    session['is_renewal'] = True

    return redirect(url_for('auth.payment'))


@auth_bp.route('/payment', methods=['GET', 'POST'])
def payment():
    restaurant_id = session.get('pending_restaurant_id')

    if not restaurant_id and 'user_id' in session:
        current_res = get_current_restaurant()
        if current_res:
            restaurant_id = current_res.id
            session['pending_restaurant_id'] = restaurant_id

    if not restaurant_id:
        return redirect(url_for('auth.register'))

    restaurant = Restaurant.query.get(restaurant_id)
    if not restaurant:
        return redirect(url_for('auth.register'))

    selected_plan_key = session.get('selected_plan', 'crecimiento')
    plan_info = SubscriptionService.get_plan_info(selected_plan_key)

    if plan_info['price_raw'] <= 0:
        flash('Plan inválido para pago. Por favor selecciona un plan de pago.')
        return redirect(url_for('auth.plans'))

    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    preference_data, _, coupon = SubscriptionService.build_mp_preference_data(
        selected_plan_key, restaurant_id, base_url
    )

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    checkout_url, preference_id, error_msg = SubscriptionService.create_mp_preference(sdk, preference_data)
    if preference_id and coupon:
        try:
            SubscriptionService.reserve_coupon(coupon, preference_id)
        except Exception:
            current_app.logger.warning('Error reservando cupón', exc_info=True)

    if error_msg:
        flash(error_msg)
        return redirect(url_for('auth.plans'))

    return redirect(checkout_url)


@auth_bp.route('/payment-callback')
def payment_callback():
    status = request.args.get('status')
    ext_ref = request.args.get('external_reference', '')

    restaurant_id = None
    plan_type = None
    if ':' in ext_ref:
        parts = ext_ref.split(':', 1)
        try:
            restaurant_id = int(parts[0])
            plan_type = parts[1]
        except (ValueError, IndexError):
            restaurant_id = None

    # La Sorpresa Velzia se entrega dentro de _finalize_payment
    # (recompensa + email), sin depender de n8n.
    restaurant, user, _ = SubscriptionService.process_payment_callback(
        status, restaurant_id, plan_type,
        payment_id=request.args.get('payment_id'),
    )

    if not restaurant:
        flash('No pudimos confirmar tu pago. Regresa e inténtalo de nuevo.')
        return redirect(url_for('auth.payment'))

    is_renewal = session.get('is_renewal', False)

    # Reset tokens on approved payment
    if status == 'approved' and user:
        mp_payment_id = request.args.get('payment_id')
        initialize_or_reset_token_wallet(user, is_reset=True, mp_payment_id=mp_payment_id)

    # Clean up session
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
        return redirect(url_for('auth.login'))
    else:
        flash('Tu pago está pendiente de aprobación. Hemos activado tu acceso temporalmente.')
        if is_renewal:
            return redirect(url_for('dashboard.subscription'))
        return redirect(url_for('auth.login'))


@auth_bp.route('/webhook', methods=['POST'])
@csrf.exempt
def webhook():
    """
    Recibe notificaciones de Mercado Pago (formato IPN legacy).
    Verifica firma HMAC cuando `MP_WEBHOOK_SECRET` está configurado.
    Para webhooks nuevos, usar `POST /api/v1/webhooks/mercadopago`.
    """
    try:
        data = request.get_json(silent=True) or {}

        payment_id = None

        if data and data.get("type") == "payment":
            payment_id = data.get("data", {}).get("id")

        if not payment_id:
            topic = request.args.get('topic') or request.args.get('type')
            if topic == 'payment':
                payment_id = request.args.get('id') or request.args.get('data.id')

        # Verificación HMAC si hay secret configurado
        webhook_secret = current_app.config.get('MP_WEBHOOK_SECRET')
        if webhook_secret and payment_id:
            ts, v1 = extract_mp_signature(request.headers)
            if not verify_mp_signature(str(payment_id), ts, v1, webhook_secret):
                current_app.logger.warning(
                    f"WEBHOOK LEGACY: Firma inválida para payment_id={payment_id}"
                )
                return jsonify({'success': False, 'error': 'invalid_signature'}), 401

        if payment_id:
            access_token = current_app.config.get('MP_ACCESS_TOKEN')
            result = SubscriptionService.process_mp_webhook_payment(payment_id, access_token)
            if result:
                current_app.logger.info(
                    f"WEBHOOK: Activated restaurant {result['restaurant_id']}"
                )

        return jsonify({'success': True}), 200
    except Exception as e:
        current_app.logger.error(f"WEBHOOK ERROR: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'internal_error'}), 500


@auth_bp.route('/logout')
def logout():
    session.clear()
    return render_template('auth/logout_clerk.html')

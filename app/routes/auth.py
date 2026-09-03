from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, current_app
from app import db
from app.forms import LoginForm
from app.forms.auth import RegisterSetupForm
from app.models import Restaurant, TrialHistory
from app.utils.subscription import initialize_or_reset_token_wallet
from app.utils.mp_webhook import extract_mp_signature, verify_mp_signature
from app.services.auth_service import AuthService
from app.services.subscription_service import SubscriptionService
from app.utils.restaurant import get_current_restaurant
import mercadopago

auth_bp = Blueprint('auth', __name__)

from app.csrf import csrf

@auth_bp.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for diagnostics."""
    checks = {}
    try:
        db.engine.connect()
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {type(e).__name__}: {e}'

    try:
        from app.models import User
        count = User.query.count()
        checks['users_table'] = f'ok ({count} users)'
    except Exception as e:
        checks['users_table'] = f'error: {type(e).__name__}: {e}'

    return jsonify({
        'status': 'ok' if all('error' not in v for v in checks.values()) else 'degraded',
        'checks': checks
    })

@auth_bp.route('/api/sync-clerk', methods=['POST'])
@csrf.exempt
def sync_clerk():
    """
    Sincroniza el usuario de Clerk con la base de datos local.
    Realiza una verificación segura consultando la API de Clerk.
    """
    try:
        data = request.get_json()
        clerk_id = data.get('clerk_id')
        email = data.get('email')
        session_id = data.get('session_id')
        current_app.logger.info(f"sync_clerk: iniciar sync email={email} clerk_id={clerk_id[:12] if clerk_id else 'None'}...")

        # 1. Verificación en el backend contra Clerk (delegada al servicio)
        verified_email, error = AuthService.verify_clerk_session(session_id, clerk_id, email)
    if error:
        return jsonify({
            'success': False,
            'message': error.get('message', 'Verification failed'),
            'error_code': error.get('error_code', 'VERIFICATION_FAILED')
        }), 401 if error.get('error_code') in ('INVALID_SESSION', 'INVALID_USER', 'EMAIL_MISMATCH', 'SESSION_USER_MISMATCH') else 500

    email = verified_email

    username = data.get('username') or email.split('@')[0]

    # El plan elegido en /planes queda en session['selected_plan'] pero el
    # servicio solo lo respeta si existe un PreRegistration. Sin esto, un
    # correo que ya usó el trial y viene a COMPRAR un plan de pago era
    # tratado como 'trial' por defecto → TRIAL_ALREADY_USED → loop
    # planes→register→login→planes. Persistirlo aquí rompe ese ciclo.
    selected_plan = session.get('selected_plan')
    if selected_plan and selected_plan != 'trial':
        try:
            AuthService.save_plan_selection(email, selected_plan)
        except Exception:
            current_app.logger.warning(
                f"sync_clerk: no se pudo persistir plan {selected_plan} para {email}",
                exc_info=True,
            )

    # 2. Delegar sync / creación de usuario al servicio
    user, is_new, plan_or_error = AuthService.sync_or_create_user(
        clerk_id, email, username
    )

    if user is None:
        # Bug 3: el correo ya usó el trial gratuito → redirigir a planes
        # con mensaje claro en vez de regalar otro trial.
        if plan_or_error.get('error_code') == 'TRIAL_ALREADY_USED':
            # El usuario tiene sesión Clerk válida pero NO cuenta local
            # (trial bloqueado). Guardar su identidad para que /planes
            # muestre logout y deshabilite el botón del plan trial, en vez
            # de tratarlo como visitante anónimo.
            session['clerk_id'] = clerk_id
            session['trial_blocked'] = True
            flash(plan_or_error.get('message'), 'warning')
            return jsonify({
                'success': True,
                'redirect_url': url_for('auth.plans'),
                'message': plan_or_error.get('message'),
                'trial_blocked': True,
            })

        return jsonify({
            'success': False,
            'message': plan_or_error.get('message', 'Error de registro'),
            'error_code': plan_or_error.get('error_code', 'REGISTRATION_ERROR')
        }), 500

    # v2.1.2: última acción de login gana. Si en este navegador había una
    # sesión de empleado (employee_id), el dueño la toma al autenticarse.
    session.pop('employee_id', None)
    session.pop('employee_login', None)
    session.pop('employee_slug', None)
    session['user_id'] = user.id
    session['username'] = user.username
    session['clerk_id'] = clerk_id

    if is_new:
        session['selected_plan'] = plan_or_error  # plan string
        # Bug 3c: "primera vez" = usuario recién creado Y sin historial de
        # trial previo. Sin esto, el frontend mostraba "trial activado" a
        # cualquiera con is_new_user=True aunque ya hubiera tenido cuenta.
        is_first_time = not TrialHistory.query.filter_by(email=email).first()
        return jsonify({
            'success': True,
            'message': f'¡Bienvenido! Completa tu registro para activar tu plan {plan_or_error}.',
            'is_new_user': True,
            'is_first_time': is_first_time,
            'trial_plan': plan_or_error == 'trial',
            'redirect_url': url_for('auth.setup_account')
        })

    redirect_url = url_for('dashboard.index')
    if not user.restaurant:
        # Usuario existente sin restaurante.
        if session.get('selected_plan'):
            # Ya eligió un plan (trial o pago en /planes → /register) → completar
            # el registro en setup-account con ese plan.
            redirect_url = url_for('auth.setup_account')
        else:
            # Sin plan elegido en esta sesión:
            #  - ya usó el trial → debe elegir un plan pago en /planes (antes caía
            #    en setup-account con plan=None → el template mostraba elite $50.000).
            #  - no usó el trial → setup con plan trial por defecto.
            already_used_trial = TrialHistory.query.filter_by(email=email).first() is not None
            if already_used_trial:
                session['clerk_id'] = clerk_id
                session['trial_blocked'] = True
                flash(
                    'Ya usaste tu período de prueba gratuito. Elige un plan para continuar.',
                    'warning'
                )
                redirect_url = url_for('auth.plans')
            else:
                session['selected_plan'] = 'trial'
                redirect_url = url_for('auth.setup_account')

    return jsonify({
        'success': True,
        'redirect_url': redirect_url
    })

    except Exception as e:
        current_app.logger.error(f"sync_clerk: ERROR FATAL: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor: {type(e).__name__}',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@auth_bp.route('/api/sync-clerk-redirect')
def sync_clerk_redirect():
    return render_template('auth/sync_clerk.html')


@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        # v2.1.1: cookie de sesión VIEJA (pre-fix) donde el login del empleado
        # guardaba user_id. Un empleado (tiene PIN) nunca debe ser tratado como
        # dueño: limpiar la sesión y mostrar el login del admin, para no quedar
        # atrapado en el loop raíz → dashboard → portal del empleado.
        if user is not None and user.pin_hash is not None:
            session.pop('user_id', None)
            session.pop('username', None)
            session.pop('clerk_id', None)
            form = LoginForm()
            return render_template('auth/index.html', form=form)
        # Cuenta logueada sin restaurante: NO ir a dashboard.index (require_active
        # lanza "Tu cuenta no está asociada a ningún restaurante" y redirige en
        # loop). Llevar al flujo correcto según su estado.
        if user and not user.restaurant:
            if session.get('selected_plan'):
                return redirect(url_for('auth.setup_account'))
            used_trial = TrialHistory.query.filter_by(email=user.email).first() is not None
            if used_trial:
                session['trial_blocked'] = True
                return redirect(url_for('auth.plans'))
            return redirect(url_for('auth.setup_account'))
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user, error = AuthService.authenticate(
            form.email.data, form.password.data
        )
        if user:
            # v2.1.2: última acción de login gana. Si en este navegador había
            # una sesión de empleado, el dueño la toma al iniciar sesión.
            session.pop('employee_id', None)
            session.pop('employee_login', None)
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
    has_restaurant = False
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        if user:
            has_restaurant = user.restaurant is not None
            # Usuario con cuenta local pero sin restaurante. Si ya usó el trial,
            # DEBE poder ver /planes para elegir un plan pago; solo se le fuerza
            # a setup-account si todavía no usó el trial (flujo de registro).
            if not user.restaurant:
                used_trial = TrialHistory.query.filter_by(email=user.email).first() is not None
                if not used_trial:
                    return redirect(url_for('auth.setup_account'))
    return render_template('auth/plans.html', has_restaurant=has_restaurant)


@auth_bp.route('/register', methods=['GET'])
def register():
    plan = request.args.get('plan')
    if plan:
        session['selected_plan'] = plan

    # Usuario ya autenticado que eligió un plan desde /planes. No debe pasar
    # por register_verify (que redirige a /login → dashboard.index → 404 por
    # require_active "sin restaurante"). Va directo a setup-account con el
    # plan ya guardado en sesión.
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        if user and not user.restaurant:
            return redirect(url_for('auth.setup_account'))

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

    # Defensivo: usuario sin restaurante que ya usó el trial y aún no eligió
    # plan. No debe quedar en setup-account con plan=None (el template lo
    # muestra como elite $50.000/mes). Forzar elección en /planes.
    if not session.get('selected_plan') and user.email:
        used_trial = TrialHistory.query.filter_by(email=user.email).first() is not None
        if used_trial:
            session['clerk_id'] = user.clerk_id
            session['trial_blocked'] = True
            flash(
                'Ya usaste tu período de prueba gratuito. Elige un plan para continuar.',
                'warning'
            )
            return redirect(url_for('auth.plans'))

    email = user.email

    if user.clerk_id:
        form.admin_name.validators = []
        form.password.validators = []
        form.confirm_password.validators = []

    if form.validate_on_submit():
        if not form.accept_terms.data:
            flash('Debes aceptar los Términos y Condiciones y la Política de Datos para continuar.', 'warning')
            return render_template('auth/register_setup.html', form=form,
                                   plan=session.get('selected_plan'), user=user)
        selected_plan = session.get('selected_plan', 'emprendedor')
        is_trial = selected_plan == 'trial'

        # Trial eligibility check
        if is_trial:
            blocked, msg = AuthService.check_trial_eligibility(
                email, form.phone.data
            )
            if blocked:
                # No dejar al usuario atascado en setup-account con plan trial:
                # redirigir a /planes para que elija un plan pago. register()
                # con user_id en sesión lo devolverá aquí con el plan ya elegido.
                session['trial_blocked'] = True
                flash(msg, 'warning')
                return redirect(url_for('auth.plans'))

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
            # Email de bienvenida justo después de crear el restaurante en DB.
            # No bloquea el flujo si el envío falla.
            AuthService.send_welcome_email(restaurant, user)
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

        # Fail-closed (alineado con /api/v1/webhooks/mercadopago): sin secret
        # configurado NO se procesa nada; con secret, la firma es obligatoria.
        webhook_secret = current_app.config.get('MP_WEBHOOK_SECRET')
        if not webhook_secret:
            current_app.logger.error("WEBHOOK LEGACY: MP_WEBHOOK_SECRET no configurado")
            return jsonify({'success': False, 'error': 'webhook_not_configured'}), 503

        if payment_id:
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

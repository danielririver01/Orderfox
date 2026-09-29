"""
Dashboard del tendero (POS) — Jinja2 + sesión, mismo patrón que core.

Rutas html (el tendero ve pantallas) y la acción de venta por sesión:
la SERVICE_API_KEY NUNCA llega al navegador. Las APIs JSON con x-api-key
quedan para integraciones server-to-server y el checkout público.
"""
from datetime import timezone

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from ..auth import require_service_api_key

from ..services import alerts as alerts_service
from ..services import catalog
from ..services import context as context_service
from ..services import pos_auth as pos_auth_service
from ..services import sales as sales_service
from ..services import scale as scale_service
from ..services.pos_auth import (
    PosAuthError,
    consume_pos_sso_token,
    current_pos_business,
    login_pos,
    logout_pos,
    request_pos_pin_reset,
    require_pos_business,
    setup_pos_pin,
)
from .dashboard_helpers import (
    _sale_for_ticket,
)

dashboard_bp = Blueprint('dashboard', __name__)


# ── Login / sesión ──────────────────────────────────────────


@dashboard_bp.route('/pos', methods=['GET'])
def pos_home():
    business = current_pos_business()
    if business:
        return redirect(url_for('dashboard.pos_view', slug=business.slug))
    return redirect(url_for('dashboard.pos_login'))


@dashboard_bp.route('/pos/login', methods=['GET', 'POST'])
def pos_login():
    if request.method == 'POST':
        identifier = request.form.get('identifier') or request.form.get('slug')
        try:
            business = login_pos(
                identifier,
                request.form.get('pin'),
                ip=request.remote_addr,
            )
        except PosAuthError as e:
            flash(str(e), 'error')
            return render_template('pos_login.html'), 401
        return redirect(url_for('dashboard.pos_view', slug=business.slug))
    return render_template('pos_login.html')


@dashboard_bp.route('/pos/logout', methods=['POST'])
def pos_logout():
    logout_pos()
    return redirect(url_for('dashboard.pos_login'))


@dashboard_bp.route('/pos/forgot-pin', methods=['GET', 'POST'])
def pos_forgot_pin():
    """Pantalla para solicitar restablecimiento del PIN del POS por correo."""
    if request.method == 'POST':
        email = request.form.get('email')
        _ok, message = request_pos_pin_reset(
            email, base_url=request.host_url.rstrip('/'))
        flash(message, 'ok')
        return redirect(url_for('dashboard.pos_login'))
    return render_template('pos_forgot_pin.html')


@dashboard_bp.route('/api/verduras/businesses/<int:business_id>/pos-pin',
                    methods=['POST'])
def api_setup_pos_pin(business_id: int):
    """Configura el PIN del POS (onboarding, server-to-server con x-api-key).

    Deliberadamente NO es una pantalla pública: permitir que cualquiera
    cree el "primer PIN" sabiendo el slug sería business squatting. El
    dashboard de core (o el provisioner) llama aquí con la service key.
    """
    try:
        require_service_api_key()
    except Exception:  # noqa: BLE001 — VerdurasAuthError es PermissionError
        return jsonify(success=False, error_code='unauthorized'), 401
    from ..services.pos_auth import PosAuthError as _PAE
    try:
        setup_pos_pin(business_id, (request.get_json(silent=True) or {}).get('pin'))
    except _PAE as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, message='PIN del POS configurado')


# ── Setup del POS con token de un solo uso (registro self-service) ──


@dashboard_bp.route('/pos/setup/<slug>/<token>', methods=['GET'])
def pos_setup_form(slug: str, token: str):
    """Pantalla de primer setup: el dueño llega desde el registro de core.

    Pre-auth POR DISEÑO: el enlace firmado en DB es la credencial (un solo
    uso). El POST igual pasa por el guard CSRF de la factory.
    """
    try:
        business = pos_auth_service.get_setup_target(slug, token)
    except PosAuthError as e:
        flash(str(e), 'error')
        return redirect(url_for('dashboard.pos_login'))
    return render_template('pos_setup.html', business=business, token=token)


@dashboard_bp.route('/pos/setup/<slug>/<token>', methods=['POST'])
def pos_setup_submit(slug: str, token: str):
    """Consume el token: configura PIN + WhatsApp y deja el POS listo."""
    pin = request.form.get('pin')
    pin2 = request.form.get('pin2')
    if pin != pin2:
        flash('Los PIN no coinciden', 'error')
        return redirect(url_for('dashboard.pos_setup_form', slug=slug,
                                token=token))
    try:
        pos_auth_service.consume_setup_token(
            slug, token, pin,
            whatsapp_phone=request.form.get('whatsapp_phone'))
    except PosAuthError as e:
        flash(str(e), 'error')
        return redirect(url_for('dashboard.pos_setup_form', slug=slug,
                                token=token))
    flash('¡Listo! Tu POS quedó configurado. Entra con tu PIN.', 'ok')
    return redirect(url_for('dashboard.pos_login'))


# ── Handoff Mundos → POS (dueño llega sin PIN) ──────────────


@dashboard_bp.route('/pos/sso/<slug>/<token>', methods=['GET'])
def pos_sso(slug: str, token: str):
    """Consume el handoff emitido por core y abre la sesión del POS.

    Pre-auth POR DISEÑO (igual que el setup): el bearer de 256 bits, de un
    solo uso y con expiración de 5 min ES la credencial. Enlace muerto o
    reusado → login de mostrador con mensaje genérico.
    """
    try:
        business = consume_pos_sso_token(slug, token)
    except PosAuthError as e:
        flash(str(e), 'error')
        return redirect(url_for('dashboard.pos_login'))
    return redirect(url_for('dashboard.pos_view', slug=business.slug))


# ── Pantallas ───────────────────────────────────────────────


@dashboard_bp.route('/pos/<slug>', methods=['GET'])
def pos_view(slug: str):
    business = current_pos_business()
    if business is None or business.slug != slug:
        return redirect(url_for('dashboard.pos_login'))
    # Ciclo de suscripción: el tendero ve el estado (vence pronto / gracia) o
    # una pantalla de renovación si ya no puede vender. Jamás un 500.
    try:
        sub = context_service.get_subscription_status(business)
    except Exception:  # noqa: BLE001 — la suscripción jamás tumba el POS
        sub = {'can_crud': True}
    if not sub.get('can_crud'):
        core_base = current_app.config.get('CORE_BASE_URL') or 'http://localhost:5000'
        return render_template(
            'pos_renewal.html', business=business, status=sub,
            core_payment_url=f'{core_base}/renew',
        )
    products = catalog.list_products(business.id)
    # Mapa product_id → severidad de alerta de rotación (Semana 5): el POS
    # pinta un badge por producto, informativo — nunca bloquea la venta.
    try:
        alerts_map = {
            str(a['product_id']): a['severity']
            for a in alerts_service.list_alerts(business.id)['alerts']
        }
    except Exception:  # noqa: BLE001 — las alertas jamás tumban el POS
        alerts_map = {}
    pos_data = {
        'scale_enabled': bool(current_app.config.get('SCALE_ENABLED', False)),
        'alerts': alerts_map,
        'products': [
            {
                'id': p.id,
                'name': p.name,
                'unit': p.unit,
                'price': str(p.current_price),
                'category_id': p.category_id,
            }
            for p in products
        ],
    }
    return render_template(
        'pos.html',
        business=business,
        categories=catalog.list_categories(business.id),
        pos_settings=sales_service.get_settings(business.id),
        pos_data=pos_data,
        pos_urls={
            'sell': url_for('dashboard.pos_sell', slug=business.slug),
            'scale': url_for('dashboard.pos_scale_weight', slug=business.slug),
        },
    )


# ── Configuración v1 (sesión del tendero, sin roles) ────────


@dashboard_bp.route('/pos/<slug>/config', methods=['GET'])
def pos_config(slug: str):
    """Pantalla de ajustes honestos: negocio, PIN, balanza (lectura) y
    suscripción (lectura + link a core). Sin sesión o slug ajeno → login.
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return redirect(url_for('dashboard.pos_login'))
    settings = sales_service.get_settings(business.id)
    try:
        sub = context_service.get_subscription_status(business)
    except Exception:  # noqa: BLE001 — la suscripción jamás tumba la vista
        sub = {'can_crud': True}
    core_base = (current_app.config.get('CORE_BASE_URL')
                 or 'http://localhost:5000').rstrip('/')
    scale = {
        'enabled': bool(current_app.config.get('SCALE_ENABLED', False)),
        'protocol': current_app.config.get('SCALE_PROTOCOL', 'generic'),
        'port': current_app.config.get('SCALE_PORT', 'COM3'),
    }
    return render_template(
        'pos_config.html',
        business=business,
        whatsapp_phone=settings.whatsapp_phone or '',
        is_open=bool(settings.is_open),
        scale=scale,
        sub_can_crud=bool(sub.get('can_crud', True)),
        sub_message=sub.get('message'),
        core_manage_url=f'{core_base}/subscription',
    )


@dashboard_bp.route('/pos/<slug>/config/negocio', methods=['POST'])
def pos_config_negocio(slug: str):
    """Guarda WhatsApp + abierto/cerrado del negocio."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        settings = sales_service.update_settings(business.id, {
            'whatsapp_phone': data.get('whatsapp_phone', ''),
            'is_open': data.get('is_open', True),
        })
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, data={
        'whatsapp_phone': settings.whatsapp_phone,
        'is_open': bool(settings.is_open),
    })


@dashboard_bp.route('/pos/<slug>/config/pin', methods=['POST'])
def pos_config_pin(slug: str):
    """Cambia el PIN verificando el actual (sin el vigente no hay cambio)."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    if (data.get('new_pin') or '') != (data.get('new_pin2') or ''):
        return jsonify(success=False,
                       error='Los PIN nuevos no coinciden'), 400
    try:
        pos_auth_service.change_pos_pin(
            business.id, data.get('current_pin'), data.get('new_pin'))
    except PosAuthError as e:
        return jsonify(success=False, error=str(e)), 401
    return jsonify(success=True, data={'updated': True})


# ── Acciones del POS (sesión, sin x-api-key) ────────────────


@dashboard_bp.route('/pos/<slug>/sell', methods=['POST'])
def pos_sell(slug: str):
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    # Segundo candado: la sesión puede seguir viva aunque la suscripción
    # haya vencido — la venta exige can_crud (mismo criterio del gate de pos_view).
    try:
        sub = context_service.get_subscription_status(business)
    except Exception:  # noqa: BLE001 — la suscripción jamás tumba el POS
        sub = {'can_crud': True}
    if not sub.get('can_crud'):
        return (jsonify(success=False, error='suscripcion_inactiva',
                        message=sub.get('message')), 409)
    data = request.get_json(silent=True) or {}
    try:
        sale, _created = sales_service.create_sale(
            business.id,
            data.get('items') or [],
            sale_type='walk_in',
            customer_name=data.get('customer_name') or '',
            payment_method=data.get('payment_method'),
            amount_received=data.get('amount_received'),
            client_id=data.get('client_id'),
            skip_open_check=True,  # venta de mostrador aunque esté "cerrado"
        )
    except sales_service.VerdurasValidationError as e:
        return jsonify(success=False, error=str(e)), 400
    except sales_service.VerdurasNotFoundError as e:
        return jsonify(success=False, error=str(e)), 404
    return jsonify(success=True, data=_sale_for_ticket(sale))


# ── Báscula digital (Semana 4) ──────────────────────────────


@dashboard_bp.route('/pos/<slug>/api/scale/weight', methods=['GET'])
def pos_scale_weight(slug: str):
    """Lee la báscula del POS (sesión del tendero; sin x-api-key).

    Nunca devuelve 500: cualquier problema de báscula es un 409 con código
    legible para el frontend, que pide ingreso manual y la venta continúa.
    La báscula es ayuda, no requisito.
    """
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    try:
        weight = scale_service.read_weight(
            enabled=current_app.config.get('SCALE_ENABLED', False),
            protocol=current_app.config.get('SCALE_PROTOCOL', 'generic'),
            port=current_app.config.get('SCALE_PORT', 'COM3'),
            baudrate=current_app.config.get('SCALE_BAUDRATE', 9600),
            timeout_s=current_app.config.get('SCALE_TIMEOUT_S', 2.0),
        )
    except scale_service.ScaleDisabledError:
        return jsonify(success=False, error_code='scale_disabled',
                       error='La báscula no está activada en este negocio'), 409
    except scale_service.ScaleUnavailableError as e:
        return jsonify(success=False, error_code='scale_unavailable',
                       error=str(e)), 409
    except scale_service.ScaleReadError as e:
        return jsonify(success=False, error_code='scale_read_error',
                       error=str(e)), 409
    return jsonify(success=True, data={'weight_kg': weight})


# ── Submódulos del dashboard (mismo Blueprint 'dashboard') ──
# Import al FINAL: dashboard_clientes/dashboard_ventas/dashboard_inventario
# hacen `from .dashboard import dashboard_bp` (ciclo parcial seguro — el
# Blueprint ya está definido arriba). Los nombres de función de vista
# se conservan intactos.
from . import (
    dashboard_clientes,  # noqa: F401
    dashboard_inventario,  # noqa: F401
    dashboard_ventas,  # noqa: F401
)

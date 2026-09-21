"""
Dashboard del tendero (POS) — Jinja2 + sesión, mismo patrón que core.

Rutas html (el tendero ve pantallas) y la acción de venta por sesión:
la SERVICE_API_KEY NUNCA llega al navegador. Las APIs JSON con x-api-key
quedan para integraciones server-to-server y el checkout público.
"""
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
from ..services import pos_auth as pos_auth_service
from ..services import sales as sales_service
from ..services import scale as scale_service
from ..services.pos_auth import (
    PosAuthError,
    current_pos_business,
    login_pos,
    logout_pos,
    setup_pos_pin,
)

dashboard_bp = Blueprint('dashboard', __name__)


def _fmt_cop(value) -> str:
    """$1.234.567,00 — formato es-CO (punto miles, coma decimales)."""
    return (f'${value:,.2f}'.replace(',', 'X')
            .replace('.', ',').replace('X', '.'))


def _sale_for_ticket(sale) -> dict:
    """Payload mínimo para pintar/imprimir el ticket en el navegador."""
    return {
        'sale_number': sale.sale_number,
        'total': _fmt_cop(sale.total),
        'items': [
            {
                'name': i.product_name,
                'qty': str(i.quantity.normalize()),
                'unit': i.unit,
                'line_total': _fmt_cop(i.line_total),
            }
            for i in sale.items
        ],
    }


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
        try:
            business = login_pos(
                request.form.get('slug'),
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


# ── Pantallas ───────────────────────────────────────────────


@dashboard_bp.route('/pos/<slug>', methods=['GET'])
def pos_view(slug: str):
    business = current_pos_business()
    if business is None or business.slug != slug:
        return redirect(url_for('dashboard.pos_login'))
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


# ── Acciones del POS (sesión, sin x-api-key) ────────────────


@dashboard_bp.route('/pos/<slug>/sell', methods=['POST'])
def pos_sell(slug: str):
    business = current_pos_business()
    if business is None or business.slug != slug:
        return jsonify(success=False, error='sesion_expirada'), 401
    data = request.get_json(silent=True) or {}
    try:
        sale, _created = sales_service.create_sale(
            business.id,
            data.get('items') or [],
            sale_type='walk_in',
            customer_name=data.get('customer_name') or '',
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

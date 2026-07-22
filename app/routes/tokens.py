"""
app/routes/tokens.py
Velzia 2.0.0 — API de Tokens IA

Endpoints:
  GET  /api/tokens/status          → Estado del wallet (requiere sesión Flask O JWT Clerk)
  POST /api/tokens/consume         → Consumir 1 token (JWT Clerk, llamado desde Scanner IA)
  POST /api/tokens/topup/initiate  → Iniciar pago MP para recarga de tokens
  GET  /api/tokens/topup/callback  → Webhook MP — acreditar tokens comprados
"""
from flask import Blueprint, jsonify, request, session, current_app, redirect, url_for, flash
from app import db
from app.models import User, AITokenTransaction
from app.csrf import csrf
from app.utils.subscription import TOP_UP_PACKS, is_subscription_active
import mercadopago
from app.services.token_service import TokenService

tokens_bp = Blueprint('tokens', __name__)


# ─── Helper: Identificar usuario desde request ────────────────────────────────

def _get_user_from_request() -> User | None:
    """
    Identifica al usuario por sesión Flask o Bearer token Clerk.

    Permanece en la capa de rutas porque depende de request y session objects.
    """
    if 'user_id' in session:
        return User.query.get(session['user_id'])

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        raw_token = auth_header[7:]
        clerk_id = TokenService.verify_clerk_jwt(raw_token)
        if clerk_id:
            return User.query.filter_by(clerk_id=clerk_id).first()

    # Soporte para Server-to-Server (S2S) con x-api-key
    api_key = request.headers.get('x-api-key')
    valid_api_key = current_app.config.get('SERVICE_API_KEY')
    if api_key and valid_api_key and api_key == valid_api_key:
        data = request.get_json(silent=True) or {}
        clerk_id = request.args.get('userId') or data.get('clerk_id')
        email = data.get('email')

        if clerk_id:
            user = User.query.filter_by(clerk_id=clerk_id).first()
            if user:
                return user

            # Auto-healing DB: vincular por email
            if email:
                user = User.query.filter_by(email=email).first()
                if user:
                    user.clerk_id = clerk_id
                    db.session.commit()
                    current_app.logger.info(
                        f"Cuenta vinculada automáticamente: {email} -> {clerk_id}"
                    )
                    return user

    return None


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@tokens_bp.route('/api/tokens/status', methods=['GET'])
def token_status():
    """Estado actual del wallet de tokens."""
    user = _get_user_from_request()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    status_data, error = TokenService.get_wallet_status(user)
    if error:
        return jsonify({'error': error['error_code']}), 404

    return jsonify(status_data)


@tokens_bp.route('/api/tokens/consume', methods=['POST'])
@csrf.exempt
def token_consume():
    """
    Consume 1 token del wallet del usuario autenticado.
    Llamado desde Scanner IA (JWT Clerk o x-api-key).
    """
    user = _get_user_from_request()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    result, error = TokenService.consume_token(user)
    if error:
        return jsonify({
            'success': False,
            'error_code': error['error_code'],
            'message': error['message'],
        }), 403

    return jsonify({
        'success': True,
        'message': 'Token consumido exitosamente',
    })


@tokens_bp.route('/api/tokens/topup/initiate', methods=['POST'])
@csrf.exempt
def topup_initiate():
    """Inicia el flujo de pago MP para comprar tokens."""
    user = _get_user_from_request()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    pack_key = data.get('pack', '25')
    pack = TOP_UP_PACKS.get(pack_key)
    if not pack:
        return jsonify({'error': 'Pack inválido'}), 400

    # Compra permitida solo con suscripción estrictamente activa (trial o plan
    # de pago). En gracia o expirada → debe activar un plan primero.
    restaurant = user.restaurant
    if restaurant and not is_subscription_active(restaurant, include_grace_period=False):
        return jsonify({
            'error': 'Tu prueba gratuita ha finalizado. Activa un plan para comprar créditos IA.',
        }), 403

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))

    preference_data = {
        "items": [{
            "title": f"Velzia Tokens — {pack['label']} (+{pack['tokens']} tokens)",
            "quantity": 1,
            "unit_price": float(pack['price_cop']),
            "currency_id": "COP",
        }],
        "back_urls": {
            "success":
                f"{base_url}/api/tokens/topup/callback"
                f"?pack={pack_key}&user={user.id}",
            "failure": f"{base_url}/dashboard",
            "pending":
                f"{base_url}/api/tokens/topup/callback"
                f"?pack={pack_key}&user={user.id}&status=pending",
        },
        "external_reference": f"token_topup:{user.id}:{pack_key}",
    }

    # auto_return solo en producción: Mercado Pago IGNORA las back_urls en
    # cuentas TEST / dominios localhost, y con auto_return="approved" exige
    # back_urls.success definido -> la preferencia se rechaza ("Error MP").
    if base_url and 'localhost' not in base_url and '127.0.0.1' not in base_url:
        preference_data["auto_return"] = "approved"

    try:
        pref_resp = sdk.preference().create(preference_data)
        if pref_resp.get('status') != 201:
            current_app.logger.error(f"MP topup error: {pref_resp}")
            msg = pref_resp.get('response', {}).get('message', 'Error al crear la preferencia de pago')
            return jsonify({'error': f'Error MP: {msg}'}), 500
        checkout_url = pref_resp['response']['init_point']
        return jsonify({'success': True, 'checkout_url': checkout_url})
    except Exception as e:
        current_app.logger.error(f"MP topup exception: {e}")
        return jsonify({'error': 'Error MP'}), 500


@tokens_bp.route('/api/tokens/topup/callback', methods=['GET'])
def topup_callback():
    """Callback MP post-recarga de tokens — SOLO INFORMATIVO.

    NO acredita tokens directamente (eso lo hace el webhook con HMAC).
    Solo muestra al usuario el estado de su pago.
    """
    status = request.args.get('status', '')
    ext_ref = request.args.get('external_reference', '')
    mp_payment_id = request.args.get('payment_id')

    if status == 'approved' and ext_ref.startswith('token_topup:'):
        if mp_payment_id:
            already = AITokenTransaction.query.filter_by(
                mp_payment_id=mp_payment_id, type='topup_purchase'
            ).first()
            if already:
                flash(f'¡{already.amount} tokens acreditados!', 'success')
            else:
                flash('Pago recibido. Los tokens se acreditarán en segundos.', 'info')
        else:
            flash('Pago recibido. Los tokens se acreditarán en segundos.', 'info')
    elif status == 'pending' or status == 'in_process':
        flash('Tu pago de tokens está pendiente.', 'info')
    else:
        flash('No pudimos confirmar tu pago de tokens.', 'error')

    return redirect(url_for('dashboard.index'))

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
from app.utils.subscription import TOP_UP_PACKS
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
    pack_key = data.get('pack', '5k')
    pack = TOP_UP_PACKS.get(pack_key)
    if not pack:
        return jsonify({'error': 'Pack inválido'}), 400

    plan_type = user.restaurant.plan_type if user.restaurant else 'trial'
    if plan_type == 'trial':
        return jsonify({
            'error': 'Los usuarios en trial no pueden comprar tokens. Elige un plan.',
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
        "auto_return": "approved",
        "external_reference": f"token_topup:{user.id}:{pack_key}",
    }

    try:
        pref_resp = sdk.preference().create(preference_data)
        checkout_url = pref_resp['response']['init_point']
        return jsonify({'success': True, 'checkout_url': checkout_url})
    except Exception as e:
        current_app.logger.error(f"MP topup error: {e}")
        return jsonify({'error': 'Error MP'}), 500


@tokens_bp.route('/api/tokens/topup/callback', methods=['GET'])
def topup_callback():
    """Callback MP post-recarga de tokens."""
    status = request.args.get('status', '')
    ext_ref = request.args.get('external_reference', '')

    if status != 'approved' or not ext_ref.startswith('token_topup:'):
        flash('No pudimos confirmar tu pago de tokens.', 'error')
        return redirect(url_for('dashboard.index'))

    # Parsear referencia externa
    try:
        _, user_id_str, pack_key = ext_ref.split(':')
        user_id = int(user_id_str)
        pack = TOP_UP_PACKS.get(pack_key)
        if not pack:
            raise ValueError("Pack no encontrado")
    except Exception as e:
        current_app.logger.error(f"Error processing top-up callback: {e}")
        flash('Referencia inválida.', 'error')
        return redirect(url_for('dashboard.index'))

    user = User.query.get(user_id)
    if not user:
        flash('Usuario no encontrado.', 'error')
        return redirect(url_for('dashboard.index'))

    mp_payment_id = request.args.get('payment_id')

    # Delegar lógica de acreditación al servicio
    result, error = TokenService.credit_topup_purchase(user, pack, mp_payment_id)
    if error:
        flash(f'Error al acreditar tokens: {error["message"]}', 'error')
        return redirect(url_for('dashboard.index'))

    # Si result es un AITokenTransaction, significa que ya estaba acreditado
    if isinstance(result, AITokenTransaction):
        flash('Pago ya acreditado.', 'info')
    else:
        flash(f"¡{pack['tokens']} tokens acreditados!", 'success')

    return redirect(url_for('dashboard.index'))

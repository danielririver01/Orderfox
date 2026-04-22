"""
app/routes/tokens.py
Velzia 2.0.0 — API de Tokens IA

Endpoints:
  GET  /api/tokens/status          → Estado del wallet (requiere sesión Flask O JWT Clerk)
  POST /api/tokens/consume          → Consumir 1 token (JWT Clerk, llamado desde Scanner IA)
  POST /api/tokens/topup/initiate   → Iniciar pago MP para recarga de tokens
  GET  /api/tokens/topup/callback   → Webhook MP — acreditar tokens comprados
"""
from flask import Blueprint, jsonify, request, session, current_app
from datetime import datetime, timezone
from app import db
from app.models import User, AITokenTransaction
from app.extensions import csrf
from app.utils.subscription import AI_TOKEN_LIMITS, TOP_UP_PACKS, initialize_or_reset_token_wallet

tokens_bp = Blueprint('tokens', __name__)

# ─── Helper: Validar Clerk JWT ─────────────────────────────────────────────────
def _verify_clerk_jwt(token: str) -> str | None:
    """
    Verifica el Bearer token de Clerk usando python-jose.
    Retorna el clerk_id (sub) si es válido, None si falla.
    """
    try:
        from jose import jwt
        import requests as req

        # Obtener JWKS de Clerk (cacheado por el proceso)
        clerk_domain = current_app.config.get('CLERK_JWT_ISSUER') or \
                       'https://oriented-tortoise-50.clerk.accounts.dev'
        
        jwks_url = f"{clerk_domain}/.well-known/jwks.json"
        
        # Simple cache en app_config
        cache_key = '_clerk_jwks_cache'
        jwks_data = current_app.config.get(cache_key)
        if not jwks_data:
            resp = req.get(jwks_url, timeout=5)
            resp.raise_for_status()
            jwks_data = resp.json()
            current_app.config[cache_key] = jwks_data

        payload = jwt.decode(
            token,
            jwks_data,
            algorithms=['RS256'],
            options={'verify_aud': False}
        )
        return payload.get('sub')

    except Exception as e:
        current_app.logger.warning(f"Clerk JWT validation failed: {e}")
        return None


def _get_user_from_request() -> User | None:
    """
    Identifica al usuario por sesión Flask o Bearer token Clerk.
    """
    if 'user_id' in session:
        return User.query.get(session['user_id'])

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        raw_token = auth_header[7:]
        clerk_id = _verify_clerk_jwt(raw_token)
        if clerk_id:
            return User.query.filter_by(clerk_id=clerk_id).first()

    return None


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@tokens_bp.route('/api/tokens/status', methods=['GET'])
def token_status():
    """Estado actual del wallet de tokens."""
    user = _get_user_from_request()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    # initialize_or_reset_token_wallet maneja creación y reset mensual automáticamente
    wallet = initialize_or_reset_token_wallet(user)
    if not wallet:
        return jsonify({'error': 'no_wallet'}), 404

    plan_type = user.restaurant.plan_type if user.restaurant else 'trial'

    return jsonify({
        'is_elite':        wallet.is_elite,
        'plan_limit':      wallet.plan_limit,
        'plan_tokens':     wallet.plan_tokens,
        'extra_tokens':    wallet.extra_tokens,
        'total_available': wallet.total_available,
        'tokens_used':     wallet.tokens_used_month,
        'usage_percent':   wallet.usage_percent,
        'can_scan':        wallet.can_scan(),
        'plan_type':       plan_type,
        'reset_at':        wallet.reset_at.isoformat() if wallet.reset_at else None,
    })


@tokens_bp.route('/api/tokens/consume', methods=['POST'])
@csrf.exempt
def token_consume():
    """Consume 1 token del wallet."""
    user = _get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401

    # Verificación extra: clerk_id del body debe coincidir con el del JWT
    data = request.get_json() or {}
    body_clerk_id = data.get('clerk_id')
    if body_clerk_id:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_clerk_id = _verify_clerk_jwt(auth_header[7:])
            if jwt_clerk_id and jwt_clerk_id != body_clerk_id:
                return jsonify({'success': False, 'message': 'Token mismatch'}), 401

    wallet = initialize_or_reset_token_wallet(user)
    if not wallet:
        return jsonify({'success': False, 'message': 'Billetera no encontrada'}), 404

    if wallet.is_elite:
        tx = AITokenTransaction(
            user_id=user.id, type='elite_scan', amount=0,
            source='scanner_ia', description='Scan ilimitado — Plan Elite'
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({
            'success': True, 'is_elite': True,
            'message': 'Scan procesado (Plan Elite)',
            'remaining': None
        })

    if not wallet.can_scan():
        return jsonify({
            'success': False, 'can_scan': False,
            'message': 'Sin tokens disponibles.',
            'remaining': 0
        }), 402

    # Descontar: primero plan_tokens, luego extra_tokens
    if wallet.plan_tokens > 0:
        wallet.plan_tokens -= 1
        source_type = 'plan'
    else:
        wallet.extra_tokens -= 1
        source_type = 'extra'

    wallet.tokens_used_month += 1

    tx = AITokenTransaction(
        user_id=user.id, type='consume', amount=-1,
        source='scanner_ia',
        description=f'Análisis IA — descontado de {source_type}_tokens'
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        'success': True,
        'is_elite': False,
        'remaining': wallet.total_available,
        'plan_tokens': wallet.plan_tokens,
        'extra_tokens': wallet.extra_tokens,
        'message': f'Token consumido. Quedan {wallet.total_available} disponibles.'
    })


@tokens_bp.route('/api/tokens/refund', methods=['POST'])
@csrf.exempt
def token_refund():
    """Reembolsar 1 token en caso de fallo técnico catastrófico."""
    user = _get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401

    wallet = initialize_or_reset_token_wallet(user)
    if not wallet or wallet.is_elite:
        return jsonify({'success': True, 'message': 'No requiere reembolso (Elite/No Wallet)'})

    # Devolver 1 token al plan_tokens
    wallet.plan_tokens += 1
    
    tx = AITokenTransaction(
        user_id=user.id, type='refund', amount=1,
        source='scanner_ia', description='Reembolso por fallo técnico OCR'
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        'success': True,
        'remaining': wallet.total_available,
        'message': 'Token reembolsado con éxito'
    })


@tokens_bp.route('/api/tokens/topup/initiate', methods=['POST'])
def topup_initiate():
    """Inicia el flujo de pago MP para comprar tokens."""
    user = _get_user_from_request()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json() or {}
    pack_key = data.get('pack', '5k')
    pack = TOP_UP_PACKS.get(pack_key)
    if not pack:
        return jsonify({'error': 'Pack inválido'}), 400

    plan_type = user.restaurant.plan_type if user.restaurant else 'trial'
    if plan_type == 'trial':
        return jsonify({'error': 'Los usuarios en trial no pueden comprar tokens. Elige un plan.'}), 403

    import mercadopago
    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))

    preference_data = {
        "items": [{
            "title": f"Velzia Tokens — {pack['label']} (+{pack['tokens']} tokens)",
            "quantity": 1,
            "unit_price": float(pack['price_cop']),
            "currency_id": "COP"
        }],
        "back_urls": {
            "success": f"{base_url}/api/tokens/topup/callback?pack={pack_key}&user={user.id}",
            "failure": f"{base_url}/dashboard",
            "pending": f"{base_url}/api/tokens/topup/callback?pack={pack_key}&user={user.id}&status=pending"
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
    from flask import redirect, url_for, flash
    status = request.args.get('status', '')
    ext_ref = request.args.get('external_reference', '')

    if status != 'approved' or not ext_ref.startswith('token_topup:'):
        flash('No pudimos confirmar tu pago de tokens.', 'error')
        return redirect(url_for('dashboard.index'))

    try:
        _, user_id_str, pack_key = ext_ref.split(':')
        user_id = int(user_id_str)
        pack = TOP_UP_PACKS.get(pack_key)
        if not pack: raise ValueError()
    except Exception:
        flash('Referencia inválida.', 'error')
        return redirect(url_for('dashboard.index'))

    user = User.query.get(user_id)
    if not user:
        flash('Usuario no encontrado.', 'error')
        return redirect(url_for('dashboard.index'))

    # initialize_or_reset_token_wallet asegura que tenga wallet
    wallet = initialize_or_reset_token_wallet(user)
    mp_payment_id = request.args.get('payment_id')

    # Anti-duplicados
    already = AITokenTransaction.query.filter_by(
        mp_payment_id=mp_payment_id, type='topup_purchase'
    ).first()
    if already:
        flash('Pago ya acreditado.', 'info')
        return redirect(url_for('dashboard.index'))

    wallet.extra_tokens += pack['tokens']

    tx = AITokenTransaction(
        user_id=user.id, type='topup_purchase', amount=pack['tokens'],
        source='mp_purchase', mp_payment_id=mp_payment_id,
        description=f"{pack['label']} — +{pack['tokens']} tokens"
    )
    db.session.add(tx)
    db.session.commit()

    flash(f"¡{pack['tokens']} tokens acreditados!", 'success')
    return redirect(url_for('dashboard.index'))

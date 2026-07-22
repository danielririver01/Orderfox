"""
api_webhooks.py — Endpoints de webhooks para pasarelas de pago y servicios externos.

Prioridad: verificación de firma HMAC + idempotencia para prevenir
reenvíos maliciosos y race conditions.
"""

import logging

from flask import Blueprint, request, jsonify, current_app

from app.services.auth_service import AuthService
from app.services.token_service import TokenService
from app.models import AITokenTransaction, User
from app.utils.mp_webhook import extract_mp_signature, verify_mp_signature
from app.utils.subscription import TOP_UP_PACKS

api_webhooks_bp = Blueprint('api_webhooks', __name__, url_prefix='/api/v1/webhooks')

logger = logging.getLogger(__name__)


def _payment_already_processed(data_id: str) -> bool:
    """Chequeo de idempotencia unificado: True si este payment_id ya fue procesado
    como suscripción (topup_plan) o como top-up de tokens (topup_purchase)."""
    if not data_id:
        return False
    return AITokenTransaction.query.filter(
        AITokenTransaction.mp_payment_id == data_id,
        AITokenTransaction.type.in_(['topup_plan', 'topup_purchase'])
    ).first() is not None


@api_webhooks_bp.route('/mercadopago', methods=['POST'])
def mercadopago_webhook():
    """Webhook de Mercado Pago (Webhooks API).

    Verifica firma HMAC-SHA256 del header `x-signature`, procesa pagos
    aprobados y acredita tokens. Es idempotente: si el `data.id` ya fue
    procesado, retorna 200 sin re-procesar.
    """
    try:
        body = request.get_json(silent=True) or {}
        headers = request.headers

        # Extraer data.id del body
        data_id = None
        if body.get('data') and body['data'].get('id'):
            data_id = str(body['data']['id'])
        if not data_id:
            data_id = str(body.get('id') or '')

        # Extraer y verificar firma
        ts, v1 = extract_mp_signature(headers)
        webhook_secret = current_app.config.get('MP_WEBHOOK_SECRET')

        if webhook_secret:
            if not data_id:
                logger.warning("WEBHOOK MP: Falta data.id en el payload")
                return jsonify({'success': False, 'error': 'missing_data_id'}), 400
            if not verify_mp_signature(data_id, ts, v1, webhook_secret):
                logger.warning(f"WEBHOOK MP: Firma inválida para data_id={data_id}")
                return jsonify({'success': False, 'error': 'invalid_signature'}), 401
        else:
            # Si no hay secret configurado, rechazamos el webhook en vez de
            # aceptarlo sin verificar (fail-closed).
            logger.error("WEBHOOK MP: MP_WEBHOOK_SECRET no configurado")
            return jsonify({'success': False, 'error': 'webhook_not_configured'}), 503

        # Idempotencia: si ya procesamos este data.id, saltar
        if _payment_already_processed(data_id):
            logger.info(f"WEBHOOK MP: data_id={data_id} ya procesado. Saltando.")
            return jsonify({'success': True, 'status': 'already_processed'}), 200

        # Procesar el pago (solo si es tipo payment)
        action_type = body.get('type', '')
        if action_type == 'payment' or body.get('action', '') == 'payment.created':
            payment_id = data_id
            access_token = current_app.config.get('MP_ACCESS_TOKEN')
            if not access_token:
                logger.error("WEBHOOK MP: MP_ACCESS_TOKEN no configurado")
                return jsonify({'success': False, 'error': 'server_config'}), 500

            # Obtener info del pago desde la API de MP para leer external_reference
            import mercadopago
            sdk = mercadopago.SDK(access_token)
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get("response")

            if payment and payment.get("status") == "approved":
                external_ref = payment.get("external_reference", "")

                if external_ref.startswith("token_topup:"):
                    # ── Token top-up flow ──
                    try:
                        _, user_id_str, pack_key = external_ref.split(":")
                        user = User.query.get(int(user_id_str))
                        pack = TOP_UP_PACKS.get(pack_key)
                        if user and pack:
                            result, error = TokenService.credit_topup_purchase(
                                user, pack, payment_id
                            )
                            if not error:
                                logger.info(
                                    f"WEBHOOK MP: Top-up {pack['tokens']} tokens para "
                                    f"usuario {user.id}"
                                )
                                return jsonify({
                                    'success': True,
                                    'status': 'topup_credited',
                                }), 200
                    except (ValueError, TypeError):
                        pass
                    logger.warning(
                        f"WEBHOOK MP: token_topup inválido: {external_ref}"
                    )
                    return jsonify({'success': True, 'status': 'topup_ignored'}), 200

                # ── Subscription activation flow (legacy) ──
                result = AuthService.process_mp_webhook_payment(
                    payment_id, access_token
                )
                if result:
                    logger.info(
                        f"WEBHOOK MP: Restaurante {result.get('restaurant_id')} activado"
                    )
                    return jsonify({
                        'success': True,
                        'status': 'processed',
                        'restaurant_id': result.get('restaurant_id'),
                    }), 200

        return jsonify({'success': True, 'status': 'no_action'}), 200

    except Exception as e:
        logger.error(f"WEBHOOK MP ERROR: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'internal_error'}), 500


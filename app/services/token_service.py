"""
TokenService — Business logic for AI token wallet operations.
Shared by tokens_bp routes (app/routes/tokens.py).

Pattern: @staticmethod methods returning (result, None) / (None, error_dict).
"""
import jwt as pyjwt
from flask import current_app
from jwt import PyJWKClient

from app import db
from app.models import AITokenTransaction, AITokenWallet
from app.utils.subscription import (
    initialize_or_reset_token_wallet,
)

# Descripciones legibles por fuente de consumo (para el log inmutable de tokens).
_AI_SOURCE_DESCRIPTIONS = {
    'scanner_ia': 'Escaneo IA',
    'copilot_vz': 'Análisis Copilot VZ',
    'cash_register': 'Análisis Centro de Caja',
}


def is_elite_user(user):
    """True si el restaurante del usuario es plan Elite.

    Elite queda exento del tope de seguimientos de Copilot (secciones 1-2 del
    plan de cierre de costos): el contador de follow-ups no se aplica a este
    plan, que conserva su comportamiento actual de seguimientos gratis.
    """
    if not user or not user.restaurant:
        return False
    return user.restaurant.plan_type == 'elite'


class TokenService:
    """Business logic for AI token wallet operations."""

    # ── Clerk JWT Verification ─────────────────────────────────

    @staticmethod
    def verify_clerk_jwt(token: str) -> str | None:
        """
        Verifica el Bearer token de Clerk usando python-jose.
        Retorna el clerk_id (sub) si es válido, None si falla.

        (Extraído de app/routes/tokens.py — _verify_clerk_jwt)
        """
        try:
            clerk_domain = current_app.config.get('CLERK_JWT_ISSUER') or \
                           'https://oriented-tortoise-50.clerk.accounts.dev'

            jwks_url = f"{clerk_domain}/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url, cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=['RS256'],
                options={'verify_aud': False},
                issuer=clerk_domain,
            )
            return payload.get('sub')

        except Exception as e:
            current_app.logger.warning(f"Clerk JWT validation failed: {e}")
            return None

    # ── Wallet Status ──────────────────────────────────────────

    @staticmethod
    def get_wallet_status(user):
        """
        Obtiene el estado completo del wallet de tokens para un usuario.

        Returns:
            (status_dict, None) on success
            (None, error_dict) on failure
        """
        if not user:
            return None, {'error_code': 'USER_NOT_FOUND',
                          'message': 'Usuario no encontrado'}

        wallet = initialize_or_reset_token_wallet(user)
        if not wallet:
            return None, {'error_code': 'NO_WALLET',
                          'message': 'No se encontró billetera de tokens'}

        plan_type = user.restaurant.plan_type if user.restaurant else 'trial'

        return {
            'is_elite':        wallet.is_elite,
            'plan_limit':      wallet.plan_limit or 0,
            'plan_tokens':     wallet.plan_tokens,
            'extra_tokens':    wallet.extra_tokens,
            'total_available': wallet.total_available,
            'tokens_used':     wallet.tokens_used_month,
            'usage_percent':   wallet.usage_percent or 0,
            'can_scan':        wallet.can_scan(),
            'plan_type':       plan_type,
            'reset_at':        wallet.reset_at.isoformat() if wallet.reset_at else None,
        }, None

    # ── Token Consumption ──────────────────────────────────────

    @staticmethod
    def consume_token(user, source='scanner_ia', with_receipt=False):
        """
        Consume (deduce) 1 token del wallet del usuario.
        Primero descuenta de plan_tokens, luego de extra_tokens.
        Para usuarios Elite, solo se registra (sin deducción).

        Args:
            user: Usuario ORM object.
            source: origen del consumo ('scanner_ia', 'copilot_vz',
                'cash_register'). Backward-compatible: default 'scanner_ia'.
            with_receipt: si es True devuelve un recibo (dict) en lugar de
                True. El recibo recuerda de qué saldo salió el token
                ('plan' o 'extra') para poder devolverlo al mismo sitio con
                TokenService.refund_token() si el análisis falla (VLZ-6).

        Returns:
            (True, None) / (receipt_dict, None) on success
            (None, error_dict) on failure
        """
        if not user:
            return None, {'error_code': 'USER_NOT_FOUND',
                          'message': 'Usuario no encontrado'}

        # Lock pesimista: SELECT ... FOR UPDATE sobre la fila del wallet.
        # Si otra petición está modificando esta misma billetera, espera
        # a que termine. Cierra el TOCTOU entre can_scan() y el decremento.
        wallet = AITokenWallet.query.filter_by(user_id=user.id).with_for_update().first()
        if not wallet:
            return None, {'error_code': 'NO_WALLET',
                          'message': 'No se encontró billetera de tokens'}

        if not wallet.can_scan():
            return None, {
                'error_code': 'INSUFFICIENT_TOKENS',
                'message': ('No tienes tokens disponibles para escanear. '
                            'Recarga tu plan o compra un pack de tokens.'),
            }

        try:
            # Deduct from plan_tokens first, then extra_tokens
            if wallet.plan_tokens > 0:
                wallet.plan_tokens -= 1
                bucket = 'plan'
            else:
                wallet.extra_tokens -= 1
                bucket = 'extra'

            wallet.tokens_used_month += 1

            tx = AITokenTransaction(
                user_id=user.id, type='consume', amount=-1,
                source=source,
                description=_AI_SOURCE_DESCRIPTIONS.get(source, 'Análisis IA'),
            )
            db.session.add(tx)

            db.session.commit()
            current_app.logger.info(
                f"WALLET: Token consumido para usuario {user.id}"
            )
            if with_receipt:
                return {'user_id': user.id, 'source': source,
                        'bucket': bucket, 'refunded': False}, None
            return True, None

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error consuming token: {e}")
            return None, {'error_code': 'CONSUME_ERROR',
                          'message': 'Error al consumir token'}

    # ── Token Refund (compensación por fallo técnico) ──────────

    @staticmethod
    def refund_token(user, receipt):
        """
        Devuelve 1 token cobrado con consume_token(..., with_receipt=True).

        Se usa cuando el análisis no llega a entregarse (caída del LLM o
        error del pipeline): el cargo ya está confirmado en la DB, así que
        la compensación es una transacción inversa, no un rollback (VLZ-6,
        decisión (b) del propietario).

        El token vuelve **al mismo saldo** del que salió: crédito del plan
        mensual → plan_tokens; crédito comprado → extra_tokens. Así una
        devolución nunca infla el saldo mensual por encima de su límite ni
        convierte créditos comprados en créditos que expiran.

        Es idempotente: el recibo se marca como devuelto, de modo que dos
        llamadas con el mismo recibo solo acreditan una vez.

        Args:
            user: Usuario ORM object.
            receipt: dict devuelto por consume_token(with_receipt=True).

        Returns:
            (True, None) si se devolvió el token
            (False, None) si no había nada que devolver (recibo vacío o ya
                compensado) — no es un error
            (None, error_dict) si la compensación falló
        """
        if not user or not receipt:
            return False, None

        if receipt.get('refunded'):
            return False, None

        source = receipt.get('source') or 'scanner_ia'

        # Mismo lock pesimista que el cobro: la devolución compite con
        # otros consumos concurrentes sobre la misma billetera.
        wallet = AITokenWallet.query.filter_by(user_id=user.id).with_for_update().first()
        if not wallet:
            return None, {'error_code': 'NO_WALLET',
                          'message': 'No se encontró billetera de tokens'}

        try:
            if receipt.get('bucket') == 'extra':
                wallet.extra_tokens += 1
            else:
                wallet.plan_tokens += 1

            # El turno fallido no cuenta como uso del mes.
            wallet.tokens_used_month = max(0, (wallet.tokens_used_month or 0) - 1)

            label = _AI_SOURCE_DESCRIPTIONS.get(source, 'Análisis IA')
            tx = AITokenTransaction(
                user_id=user.id, type='refund', amount=1,
                source=source,
                description=f'Devolución por fallo técnico — {label}',
            )
            db.session.add(tx)

            db.session.commit()
            receipt['refunded'] = True
            current_app.logger.info(
                f"WALLET: Token devuelto a usuario {user.id} (fuente={source})"
            )
            return True, None

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error refunding token: {e}")
            return None, {'error_code': 'REFUND_ERROR',
                          'message': 'Error al devolver el token'}

    # ── Top-Up (Purchase Credit) ───────────────────────────────

    @staticmethod
    def credit_topup_purchase(user, pack, mp_payment_id):
        """
        Acredita tokens comprados vía Mercado Pago (top-up).

        Anti-duplicado: si el mp_payment_id ya fue procesado, retorna
        la transacción existente como resultado (no es un error).

        Args:
            user: User ORM object
            pack: Pack dict from TOP_UP_PACKS
            mp_payment_id: Mercado Pago payment ID string or None

        Returns:
            (wallet_or_tx, None) on success
            (None, error_dict) on failure
        """
        if not user:
            return None, {'error_code': 'USER_NOT_FOUND',
                          'message': 'Usuario no encontrado'}

        if not pack:
            return None, {'error_code': 'INVALID_PACK',
                          'message': 'Paquete inválido'}

        # ── Anti-duplicados ──
        if mp_payment_id:
            already = AITokenTransaction.query.filter_by(
                mp_payment_id=mp_payment_id, type='topup_purchase'
            ).first()
            if already:
                current_app.logger.info(
                    f"WALLET: Pago {mp_payment_id} ya acreditado. Saltando."
                )
                return already, None

        wallet = initialize_or_reset_token_wallet(user)
        if not wallet:
            return None, {'error_code': 'NO_WALLET',
                          'message': 'No se encontró billetera de tokens'}

        try:
            # UPDATE atómico — incrementa extra_tokens directo en la DB sin
            # pasar por el ORM identity map. Previene race conditions donde
            # dos requests concurrentes leerían el mismo valor y lo
            # sobreescribirían (lost update).
            AITokenWallet.query.filter_by(id=wallet.id).update(
                {AITokenWallet.extra_tokens: AITokenWallet.extra_tokens + pack['tokens']}
            )

            tx = AITokenTransaction(
                user_id=user.id, type='topup_purchase',
                amount=pack['tokens'],
                source='mp_purchase',
                mp_payment_id=mp_payment_id,
                description=f"{pack['label']} — +{pack['tokens']} tokens",
            )
            db.session.add(tx)
            db.session.commit()
            current_app.logger.info(
                f"WALLET: Acreditados {pack['tokens']} tokens a usuario {user.id}"
            )
            return wallet, None

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error crediting topup tokens: {e}")
            return None, {'error_code': 'CREDIT_ERROR',
                          'message': 'Error al acreditar tokens'}

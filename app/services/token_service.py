"""
TokenService — Business logic for AI token wallet operations.
Shared by tokens_bp routes (app/routes/tokens.py).

Pattern: @staticmethod methods returning (result, None) / (None, error_dict).
"""
from datetime import datetime, timezone
from flask import current_app
from app import db
from jose import jwt
import requests as req
from app.models import User, AITokenWallet, AITokenTransaction
from app.utils.subscription import initialize_or_reset_token_wallet, TOP_UP_PACKS


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
            'plan_limit':      wallet.plan_limit or 300,
            'plan_tokens':     wallet.plan_tokens if not wallet.is_elite else 300,
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
    def consume_token(user):
        """
        Consume (deduce) 1 token del wallet del usuario.
        Primero descuenta de plan_tokens, luego de extra_tokens.
        Para usuarios Elite, solo se registra (sin deducción).

        Returns:
            (True, None) on success
            (None, error_dict) on failure
        """
        if not user:
            return None, {'error_code': 'USER_NOT_FOUND',
                          'message': 'Usuario no encontrado'}

        wallet = initialize_or_reset_token_wallet(user)
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
            if wallet.is_elite:
                # Elite: no deduction, just log the scan
                tx = AITokenTransaction(
                    user_id=user.id, type='elite_scan', amount=0,
                    source='scanner_ia',
                    description='Escaneo IA (Plan Elite — sin costo)',
                )
                db.session.add(tx)
            else:
                # Deduct from plan_tokens first, then extra_tokens
                if wallet.plan_tokens > 0:
                    wallet.plan_tokens -= 1
                else:
                    wallet.extra_tokens -= 1

                wallet.tokens_used_month += 1

                tx = AITokenTransaction(
                    user_id=user.id, type='consume', amount=-1,
                    source='scanner_ia',
                    description='Escaneo IA',
                )
                db.session.add(tx)

            db.session.commit()
            current_app.logger.info(
                f"WALLET: Token consumido para usuario {user.id}"
            )
            return True, None

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error consuming token: {e}")
            return None, {'error_code': 'CONSUME_ERROR',
                          'message': 'Error al consumir token'}

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
            wallet.extra_tokens += pack['tokens']

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

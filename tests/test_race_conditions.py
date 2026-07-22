"""
Tests de concurrencia para verificar que las protecciones contra race conditions
funcionan correctamente.

NOTA SOBRE SQLite vs MySQL:
  Las protecciones reales contra race conditions dependen de:
    - SELECT ... FOR UPDATE (row lock) → solo MySQL/PostgreSQL
    - UPDATE ... SET col = col + N (atómico a nivel DB) → funciona en ambos
  SQLite no soporta FOR UPDATE (no-op) y tiene limitaciones de concurrencia.
  Estos tests verifican la CORRECCIÓN LÓGICA del patrón probado.
  Para validación real de concurrencia, ejecutar los k6 tests contra MySQL.

Protecciones cubiertas:
  P1. order_service.py:generate_order_number() — with_for_update() sobre OrderCounter
  P2. token_service.py:consume_token() — with_for_update() y patrón consume seguro
  P3. subscription.py:initialize_or_reset_token_wallet() — lock pesimista en creación
  P4. token_service.py:credit_topup_purchase() — UPDATE atómico sin leer primero
  P5. subscription.py:452 (reset) — UPDATE atómico evita lost updates
  P6. api_webhooks.py:94-101 — idempotencia por mp_payment_id
  P7. order_service.py:142-144 — validacion quantity <= 0
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models import (
    AITokenWallet, AITokenTransaction, OrderCounter, Order
)
from app.services.order_service import OrderService
from app.services.token_service import TokenService
from app.utils.subscription import (
    initialize_or_reset_token_wallet,
    TOP_UP_PACKS,
)
from app.utils.rate_limiter import OrderRateLimiter


# ═══════════════════════════════════════════════════════════════════════
# P1 — ORDER NUMBER GENERATION
# ═══════════════════════════════════════════════════════════════════════

class TestOrderNumberRaceCondition:

    def test_generate_order_number_sequential(self, db, sample_restaurant):
        d0 = OrderService.generate_order_number(sample_restaurant.id)
        d1 = OrderService.generate_order_number(sample_restaurant.id)
        d2 = OrderService.generate_order_number(sample_restaurant.id)

        assert d0 == 'ORD-001'
        assert d1 == 'ORD-002'
        assert d2 == 'ORD-003'

        counter = OrderCounter.query.filter_by(
            restaurant_id=sample_restaurant.id
        ).first()
        assert counter.counter == 3

    def test_order_counter_ordering(self, db, sample_restaurant):
        """Verifica que el scheme ORD-XXX sea secuencial y correcto."""
        nums = []
        for i in range(5):
            nums.append(OrderService.generate_order_number(sample_restaurant.id))
        assert nums == ['ORD-001', 'ORD-002', 'ORD-003', 'ORD-004', 'ORD-005']

        counter = OrderCounter.query.filter_by(
            restaurant_id=sample_restaurant.id
        ).first()
        assert counter.counter == 5

    def test_order_counter_uses_with_for_update(self):
        """Verifica que generate_order_number llama a with_for_update().
        Esto es un test estructural: revisa que el método use row lock."""
        import inspect
        source = inspect.getsource(OrderService.generate_order_number)
        assert '.with_for_update()' in source, (
            "generate_order_number() debe usar with_for_update()"
        )
        assert 'db.session.flush()' in source, (
            "generate_order_number() debe hacer flush() antes de retornar"
        )


# ═══════════════════════════════════════════════════════════════════════
# P2 — TOKEN CONSUMPTION (consume_token)
# ═══════════════════════════════════════════════════════════════════════

class TestTokenConsumeRaceCondition:

    def test_consume_token_reduces_correctly(self, db, sample_user):
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        ok, err = TokenService.consume_token(sample_user)
        assert ok is True
        assert err is None

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 4
        assert wallet.tokens_used_month == 1

    def test_consume_token_uses_plan_first_then_extra(self, db, sample_user):
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=2,
            extra_tokens=3, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        for _ in range(3):
            TokenService.consume_token(sample_user)

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 0
        assert wallet.extra_tokens == 2
        assert wallet.tokens_used_month == 3

    def test_consume_token_blocks_when_empty(self, db, sample_user):
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=0,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        ok, err = TokenService.consume_token(sample_user)
        assert ok is None
        assert err is not None
        assert err.get('error_code') == 'INSUFFICIENT_TOKENS'

    def test_consume_token_uses_with_for_update(self):
        """Test estructural: verifica que consume_token use row lock."""
        import inspect
        source = inspect.getsource(TokenService.consume_token)
        assert '.with_for_update()' in source, (
            "consume_token() debe usar with_for_update()"
        )
        assert 'wallet.plan_tokens' in source or 'wallet.extra_tokens' in source

    def test_consume_sequential_no_overdraft(self, db, sample_user):
        """Consumo secuencial verifica que la lógica previene overdraft."""
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        for _ in range(5):
            ok, _ = TokenService.consume_token(sample_user)
            assert ok is True

        ok, err = TokenService.consume_token(sample_user)
        assert ok is None
        assert err is not None
        assert err.get('error_code') == 'INSUFFICIENT_TOKENS'

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 0
        assert wallet.tokens_used_month == 5
        assert wallet.total_available == 0

    def test_consume_overdraft_edge_case(self, db, sample_user):
        """Caso borde: agotar plan_tokens exactamente y que quede en 0."""
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=1,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        ok, _ = TokenService.consume_token(sample_user)
        assert ok is True

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 0

    def test_consume_drains_extra_after_plan(self, db, sample_user):
        """Consume plan_tokens hasta 0, luego consume extra_tokens."""
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=1,
            extra_tokens=3, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        for i in range(4):
            ok, _ = TokenService.consume_token(sample_user)
            assert ok is True, f"Fallo en consumo #{i + 1}"

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 0
        assert wallet.extra_tokens == 0

        ok, err = TokenService.consume_token(sample_user)
        assert ok is None


# ═══════════════════════════════════════════════════════════════════════
# P4 — TOP-UP / CREDIT (UPDATE atómico)
# ═══════════════════════════════════════════════════════════════════════

class TestTopUpRaceCondition:

    def test_topup_adds_tokens(self, db, sample_user):
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        pack = TOP_UP_PACKS['50']
        result, err = TokenService.credit_topup_purchase(
            sample_user, pack, 'mp_test_001'
        )
        assert err is None
        assert result is not None

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.extra_tokens == 50

    def test_topup_idempotent(self, db, sample_user):
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        pack = TOP_UP_PACKS['50']
        TokenService.credit_topup_purchase(sample_user, pack, 'mp_test_002')
        TokenService.credit_topup_purchase(sample_user, pack, 'mp_test_002')

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.extra_tokens == 50

    def test_topup_uses_atomic_update(self):
        """Test estructural: credit_topup_purchase debe usar UPDATE atómico
        (no leer, modificar, escribir) para evitar lost updates."""
        import inspect
        source = inspect.getsource(TokenService.credit_topup_purchase)
        assert '.update(' in source and '+ pack' in source, (
            "credit_topup_purchase() debe usar UPDATE atómico con incremento"
        )

    def test_topup_multiple_different_payments(self, db, sample_user):
        """Múltiples top-ups con distintos mp_payment_id se acumulan."""
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        packs = [
            ('mp_001', TOP_UP_PACKS['25']),
            ('mp_002', TOP_UP_PACKS['50']),
            ('mp_003', TOP_UP_PACKS['100']),
        ]
        for pid, pack in packs:
            TokenService.credit_topup_purchase(sample_user, pack, pid)

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        expected = 25 + 50 + 100
        assert wallet.extra_tokens == expected

    def test_topup_duplicate_mp_id_rejected(self, db, sample_user):
        """Mismo mp_payment_id no duplica transacciones."""
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        pack = TOP_UP_PACKS['25']
        for _ in range(3):
            TokenService.credit_topup_purchase(sample_user, pack, 'mp_dup')

        txs = AITokenTransaction.query.filter_by(mp_payment_id='mp_dup').all()
        assert len(txs) == 1

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.extra_tokens == 25


# ═══════════════════════════════════════════════════════════════════════
# P3 — WALLET CREATION (lock pesimista)
# ═══════════════════════════════════════════════════════════════════════

class TestWalletCreateRaceCondition:

    def test_wallet_creates_once(self, db, sample_user):
        wallet = initialize_or_reset_token_wallet(sample_user)
        assert wallet is not None
        assert wallet.user_id == sample_user.id
        assert wallet.plan_tokens > 0

    def test_wallet_idempotent(self, db, sample_user):
        w1 = initialize_or_reset_token_wallet(sample_user)
        w2 = initialize_or_reset_token_wallet(sample_user)
        assert w1.id == w2.id

        wallets = AITokenWallet.query.filter_by(user_id=sample_user.id).all()
        assert len(wallets) == 1

    def test_wallet_creation_uses_with_for_update(self):
        """Test estructural: wallet creation debe usar with_for_update()."""
        import inspect
        source = inspect.getsource(initialize_or_reset_token_wallet)
        assert '.with_for_update()' in source

    def test_wallet_transaction_logged(self, db, sample_user):
        """Crear wallet genera transacción topup_plan."""
        initialize_or_reset_token_wallet(sample_user)

        txs = AITokenTransaction.query.filter_by(
            user_id=sample_user.id, type='topup_plan'
        ).all()
        assert len(txs) == 1

    def test_wallet_reset_uses_atomic_update(self):
        """Test estructural: reset de wallet usa UPDATE atómico."""
        import inspect
        source = inspect.getsource(initialize_or_reset_token_wallet)
        assert '.update({' in source, "Wallet reset debe usar UPDATE atómico"


# ═══════════════════════════════════════════════════════════════════════
# P7 — QUANTITY VALIDATION
# ═══════════════════════════════════════════════════════════════════════

class TestQuantityValidation:

    def test_negative_quantity_raises(self, db, sample_restaurant, sample_product):
        order = OrderService.create_order(
            sample_restaurant.id, {'customer_name': 'Test'}
        )
        items = [{'product_id': sample_product.id, 'quantity': -1}]
        with pytest.raises(ValueError, match='Cantidad inválida'):
            OrderService.add_items_to_order(order, items, sample_restaurant.id)

    def test_zero_quantity_raises(self, db, sample_restaurant, sample_product):
        order = OrderService.create_order(
            sample_restaurant.id, {'customer_name': 'Test'}
        )
        items = [{'product_id': sample_product.id, 'quantity': 0}]
        with pytest.raises(ValueError, match='Cantidad inválida'):
            OrderService.add_items_to_order(order, items, sample_restaurant.id)

    def test_negative_quantity_no_negative_total(self, db, sample_restaurant, sample_product):
        order = OrderService.create_order(
            sample_restaurant.id, {'customer_name': 'Test'}
        )
        items = [{'product_id': sample_product.id, 'quantity': -5}]
        with pytest.raises(ValueError):
            OrderService.add_items_to_order(order, items, sample_restaurant.id)
        assert order.total == 0

    def test_valid_quantity_works(self, db, sample_restaurant, sample_product):
        order = OrderService.create_order(
            sample_restaurant.id, {'customer_name': 'Test'}
        )
        items = [{'product_id': sample_product.id, 'quantity': 3}]
        total, validated = OrderService.add_items_to_order(
            order, items, sample_restaurant.id
        )
        assert total == sample_product.price * 3
        assert len(validated) == 1


# ═══════════════════════════════════════════════════════════════════════
# P6 — WEBHOOK IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════════

class TestWebhookIdempotency:

    def test_mp_payment_id_unique_enforced(self, db, sample_user):
        """La DB no permite insertar dos transacciones con el mismo mp_payment_id."""
        tx1 = AITokenTransaction(
            user_id=sample_user.id, type='topup_purchase',
            amount=50, source='mp_purchase',
            mp_payment_id='mp_unique_001', description='Test 1',
        )
        db.session.add(tx1)
        db.session.commit()

        tx2 = AITokenTransaction(
            user_id=sample_user.id, type='topup_plan',
            amount=50, source='plan_renewal',
            mp_payment_id='mp_unique_001', description='Test 2',
        )
        db.session.add(tx2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

    def test_webhook_idempotency_check_in_topup(self, db, sample_user):
        """credit_topup_purchase chequea duplicados antes de acreditar."""
        wallet = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        pack = TOP_UP_PACKS['50']
        TokenService.credit_topup_purchase(sample_user, pack, 'mp_idem_002')
        TokenService.credit_topup_purchase(sample_user, pack, 'mp_idem_002')

        txs = AITokenTransaction.query.filter_by(
            mp_payment_id='mp_idem_002'
        ).all()
        assert len(txs) == 1

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.extra_tokens == 50

    def test_webhook_checks_before_update(self):
        """Test estructural: webhook debe verificar mp_payment_id existente."""
        import inspect
        source = inspect.getsource(TokenService.credit_topup_purchase)
        assert 'mp_payment_id' in source
        assert 'already' in source

    def test_webhook_mp_payment_id_unique_constraint(self):
        """Test estructural: el modelo tiene unique=True en mp_payment_id."""
        col = AITokenTransaction.__table__.columns['mp_payment_id']
        assert col.unique is True


# ═══════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimiterConcurrency:

    def test_rate_limiter_blocks_after_limit(self, db, sample_restaurant):
        ip = '10.0.0.100'
        for i in range(3):
            db.session.add(Order(
                restaurant_id=sample_restaurant.id,
                order_number=f'ORD-RL-{i}', customer_name=f'RL-{i}',
                total=1000, status='pending', ip_address=ip,
            ))
        db.session.commit()

        should_block, msg, wait = OrderRateLimiter.should_block_request(
            sample_restaurant.id, ip
        )
        assert should_block is True
        assert msg is not None
        assert wait is not None

    def test_rate_limiter_allows_under_limit(self, db, sample_restaurant):
        should_block, msg, wait = OrderRateLimiter.should_block_request(
            sample_restaurant.id, '10.0.0.200'
        )
        assert should_block is False


# ═══════════════════════════════════════════════════════════════════════
# ORDER STATUS TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════

class TestOrderStatusTransitions:

    def test_delivered_to_cancelled_invalid(self, db):
        assert OrderService.validate_status_transition('delivered', 'cancelled') is False

    def test_pending_to_delivered_invalid(self, db):
        assert OrderService.validate_status_transition('pending', 'delivered') is False

    def test_cancelled_to_confirmed_invalid(self, db):
        assert OrderService.validate_status_transition('cancelled', 'confirmed') is False

    def test_pending_to_confirmed_valid(self, db):
        assert OrderService.validate_status_transition('pending', 'confirmed') is True

    def test_confirmed_to_delivered_valid(self, db):
        assert OrderService.validate_status_transition('confirmed', 'delivered') is True

    def test_pending_to_expired_valid(self, db):
        assert OrderService.validate_status_transition('pending', 'expired') is True

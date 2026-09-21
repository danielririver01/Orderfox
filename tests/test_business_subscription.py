"""
Tests del ciclo de suscripción de businesses (verticales directos).

Cubren:
- get_business_subscription_status: activa, expiring_soon, grace_period,
  expired, dormant, pending_payment, cancellation_pending y el caso legacy
  (business sin dueño ni fecha — piloto — NUNCA se bloquea).
- Scheduler: _lifecycle_businesses marca dormant a vencidos + grace y
  cancellation_pending vencidas; NO toca ni espejos ni vigentes.
- activate_business_from_payment: activa, sube plan, extiende desde vencido
  y desde vigente, es idempotente por payment_id (marcador tx wallet).
- Webhook MP con referencia `biz:` (activación + return contract).
- Callback /payment-callback con `biz:` (end-to-end con sesión).
"""
from datetime import datetime, timedelta, timezone

from app.models import Business, Restaurant, User
from app.services.subscription_service import SubscriptionService
from app.tasks import _lifecycle_businesses
from app.utils.subscription import (
    GRACE_PERIOD_DAYS,
    get_business_subscription_status,
)

_user_seq = iter(__import__('itertools').count(900))


def _mk_user(db, email):
    user = User(username=f'Dueño {next(_user_seq)}', email=email,
                password='x-no-hash-needed')
    db.session.add(user)
    db.session.commit()
    return user


def _mk_biz(db, email='biz-sub@test.com', *, owner=True, expires_in=30,
            state='active', plan='trial', is_active=True):
    user = _mk_user(db, email) if owner else None
    biz = Business.create_direct('verduras', 'Verduras El Ciclo',
                                 f'ciclo-{next(_user_seq)}')
    biz.owner_user_id = user.id if user else None
    biz.plan_type = plan
    biz.subscription_state = state
    if expires_in is not None:
        biz.subscription_expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in))
    biz.is_active = is_active
    db.session.commit()
    return biz, user


def _csrf_token(client, app):
    """Patrón del proyecto (test_account_deletion.py)."""
    from itsdangerous import URLSafeTimedSerializer
    raw = 'test-csrf-raw-token'
    with client.session_transaction() as sess:
        sess['csrf_token'] = raw
    ser = URLSafeTimedSerializer(app.secret_key, salt='wtf-csrf-token')
    return ser.dumps(raw)


# ═════════════════ Status (máquina de estados) ═════════════════


class TestBusinessSubscriptionStatus:
    def test_active_with_days_remaining(self, db):
        biz, _ = _mk_biz(db, 's1@test.com', expires_in=30)
        status = get_business_subscription_status(biz)
        assert status['is_active'] is True
        assert status['status'] == 'active'
        assert status['can_crud'] is True

    def test_expiring_soon_band(self, db):
        biz, _ = _mk_biz(db, 's2@test.com', expires_in=5)
        status = get_business_subscription_status(biz)
        assert status['status'] == 'expiring_soon'
        assert status['is_active'] is True  # aún puede vender
        assert status['can_crud'] is True

    def test_grace_period_blocks_crud(self, db):
        biz, _ = _mk_biz(db, 's3@test.com', expires_in=-2)
        status = get_business_subscription_status(biz)
        assert status['status'] == 'grace_period'
        assert status['can_crud'] is False
        assert status['days_grace_remaining'] >= 1

    def test_expired_after_grace(self, db):
        biz, _ = _mk_biz(db, 's4@test.com',
                         expires_in=-(GRACE_PERIOD_DAYS + 3))
        status = get_business_subscription_status(biz)
        assert status['status'] == 'expired'
        assert status['can_crud'] is False

    def test_dormant_message_offers_reactivation(self, db):
        biz, _ = _mk_biz(db, 's5@test.com', state='dormant',
                         is_active=False, expires_in=-40)
        status = get_business_subscription_status(biz)
        assert status['status'] == 'dormant'
        assert status['can_crud'] is False

    def test_pending_payment_for_paid_plan_inactive(self, db):
        biz, _ = _mk_biz(db, 's6@test.com', plan='emprendedor',
                         is_active=False, expires_in=None)
        status = get_business_subscription_status(biz)
        assert status['status'] == 'pending_payment'
        assert status['can_crud'] is False

    def test_cancellation_pending_still_sells_until_date(self, db):
        biz, _ = _mk_biz(db, 's7@test.com', state='cancellation_pending',
                         expires_in=10)
        status = get_business_subscription_status(biz)
        assert status['status'] == 'cancellation_pending'
        assert status['can_crud'] is True

    def test_legacy_business_without_expiry_never_blocked(self, db):
        """Piloto / onboarding asistido: Business sin dueño ni fecha sigue
        vendiendo (backward-compatible)."""
        biz, _ = _mk_biz(db, owner=False, expires_in=None)
        status = get_business_subscription_status(biz)
        assert status['is_active'] is True
        assert status['can_crud'] is True

    def test_none_business_safe(self, db):
        status = get_business_subscription_status(None)
        assert status['can_crud'] is False


# ═════════════════ Scheduler (dormant) ═════════════════


class TestBusinessLifecycle:
    def test_expired_past_grace_marked_dormant(self, app, db):
        biz, _ = _mk_biz(db, 'l1@test.com',
                         expires_in=-(GRACE_PERIOD_DAYS + 2))
        now = datetime.now(timezone.utc)
        grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)
        with app.app_context():
            count = _lifecycle_businesses(grace_cutoff, now)
        assert count >= 1
        db.session.expire_all()
        stored = db.session.get(Business, biz.id)
        assert stored.subscription_state == 'dormant'
        assert stored.is_active is False
        assert stored.dormant_at is not None

    def test_pending_cancellation_marked_dormant(self, app, db):
        biz, _ = _mk_biz(db, 'l2@test.com', state='cancellation_pending',
                         expires_in=-1)
        now = datetime.now(timezone.utc)
        with app.app_context():
            _lifecycle_businesses(now - timedelta(days=GRACE_PERIOD_DAYS),
                                  now)
        db.session.expire_all()
        assert db.session.get(Business, biz.id).subscription_state == 'dormant'

    def test_active_and_grace_untouched(self, app, db):
        active, _ = _mk_biz(db, 'l3@test.com', expires_in=20)
        grace, _ = _mk_biz(db, 'l4@test.com', expires_in=-2)
        now = datetime.now(timezone.utc)
        with app.app_context():
            _lifecycle_businesses(now - timedelta(days=GRACE_PERIOD_DAYS),
                                  now)
        db.session.expire_all()
        assert db.session.get(Business, active.id).subscription_state == 'active'
        assert db.session.get(Business, grace.id).subscription_state == 'active'

    def test_restaurant_mirrors_untouched(self, app, db):
        """Espejo (sin dueño): su ciclo vive en la fila Restaurant — el
        scheduler de businesses NO lo toca."""
        r = Restaurant(name='Rest Ciclo', slug='rest-ciclo',
                       whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.commit()
        mirror = Business.query.filter_by(id=r.id).first()
        mirror.subscription_expires_at = (
            datetime.now(timezone.utc) - timedelta(days=GRACE_PERIOD_DAYS + 5))
        db.session.commit()
        now = datetime.now(timezone.utc)
        with app.app_context():
            _lifecycle_businesses(now - timedelta(days=GRACE_PERIOD_DAYS),
                                  now)
        db.session.expire_all()
        assert db.session.get(Business, r.id).subscription_state == 'active'


# ═════════════════ Pagos (activación idempotente) ═════════════════


class TestActivateBusinessFromPayment:
    def test_activates_dormant_and_extends(self, db):
        biz, owner = _mk_biz(db, 'p1@test.com', state='dormant',
                             is_active=False, expires_in=-35,
                             plan='emprendedor')
        result = SubscriptionService.activate_business_from_payment(
            biz.id, 'emprendedor', payment_id='MP-BIZ-1')
        assert result.is_active is True
        assert result.subscription_state == 'active'
        assert result.dormant_at is None
        assert result.plan_type == 'emprendedor'
        remaining = (result.subscription_expires_at
                     - datetime.now(timezone.utc)).days
        assert remaining >= 29
        # Marcador de pago creado (idempotencia callback↔webhook)
        from app.models import AITokenTransaction
        tx = AITokenTransaction.query.filter_by(
            mp_payment_id='MP-BIZ-1', type='topup_plan').first()
        assert tx is not None and tx.user_id == owner.id

    def test_extends_from_active_subscription(self, db):
        biz, _ = _mk_biz(db, 'p2@test.com', plan='emprendedor',
                         expires_in=10)
        before = biz.subscription_expires_at
        SubscriptionService.activate_business_from_payment(
            biz.id, 'emprendedor', payment_id='MP-BIZ-2')
        assert biz.subscription_expires_at > before

    def test_idempotent_by_payment_id(self, db):
        biz, _ = _mk_biz(db, 'p3@test.com', plan='crecimiento',
                         expires_in=-40)
        first = SubscriptionService.activate_business_from_payment(
            biz.id, 'crecimiento', payment_id='MP-BIZ-3')
        expires_after_first = first.subscription_expires_at
        # Reintento (mismo pago — webhook después del callback): sin efectos.
        second = SubscriptionService.activate_business_from_payment(
            biz.id, 'crecimiento', payment_id='MP-BIZ-3')
        assert second.subscription_expires_at == expires_after_first

    def test_invalid_plan_ignored(self, db):
        biz, _ = _mk_biz(db, 'p4@test.com')
        SubscriptionService.activate_business_from_payment(biz.id, 'plata')
        assert biz.plan_type != 'plata'

    def test_missing_business_returns_none(self, db):
        assert SubscriptionService.activate_business_from_payment(
            9_999_999, 'crecimiento') is None


class TestWebhookBizReference:
    def test_webhook_biz_reference_activates(self, app, db, monkeypatch):
        biz, _ = _mk_biz(db, 'w1@test.com', plan='crecimiento',
                         is_active=False, expires_in=None)

        class FakePaymentSDK:
            def payment(self):
                return self

            def get(self, _pid):
                return {'response': {
                    'status': 'approved',
                    'external_reference': f'biz:{biz.id}:crecimiento',
                    'preference_id': 'pref-biz-1',
                }}

        monkeypatch.setattr(
            'mercadopago.SDK', lambda _token: FakePaymentSDK())
        result = SubscriptionService.process_mp_webhook_payment(
            'MP-WEB-1', 'test-token')
        assert result == {'business_id': biz.id, 'plan_type': 'crecimiento'}
        db.session.expire_all()
        stored = db.session.get(Business, biz.id)
        assert stored.is_active is True
        assert stored.subscription_state == 'active'

    def test_webhook_biz_invalid_plan_ignored(self, monkeypatch):
        class FakePaymentSDK:
            def payment(self):
                return self

            def get(self, _pid):
                return {'response': {
                    'status': 'approved',
                    'external_reference': 'biz:123456:plata',
                }}

        monkeypatch.setattr(
            'mercadopago.SDK', lambda _token: FakePaymentSDK())
        assert SubscriptionService.process_mp_webhook_payment(
            'MP-WEB-2', 'test-token') is None


# ═════════════════ Callback web (`biz:`) ═════════════════


class TestPaymentCallbackBiz:
    def test_biz_callback_end_to_end(self, client, app, db):
        biz, owner = _mk_biz(db, 'cb1@test.com', plan='emprendedor',
                             is_active=False, expires_in=None)
        with client.session_transaction() as sess:
            sess['user_id'] = owner.id
            sess['pending_business_id'] = biz.id
            sess['selected_plan'] = 'emprendedor'

        res = client.get(
            f'/payment-callback?status=approved'
            f'&external_reference=biz:{biz.id}:emprendedor'
            f'&payment_id=MP-CB-1',
            follow_redirects=False)
        assert res.status_code == 302
        assert f"/register/verduras/ready/{biz.slug}" in res.headers['Location']

        db.session.expire_all()
        stored = db.session.get(Business, biz.id)
        assert stored.is_active is True
        assert stored.subscription_state == 'active'

        # La sesión quedó limpia (sin pending ni plan)
        with client.session_transaction() as sess:
            assert 'pending_business_id' not in sess
            assert 'selected_plan' not in sess

    def test_biz_callback_pending_keeps_inactive(self, client, app, db):
        """Pago pendiente (no aprobado): el Business NO se activa — espejo
        exacto del flujo de restaurantes (solo approved activa)."""
        biz, owner = _mk_biz(db, 'cb2@test.com', plan='emprendedor',
                             is_active=False, expires_in=None)
        with client.session_transaction() as sess:
            sess['user_id'] = owner.id

        res = client.get(
            f'/payment-callback?status=pending'
            f'&external_reference=biz:{biz.id}:emprendedor'
            f'&payment_id=MP-CB-PENDING',
            follow_redirects=False)
        assert res.status_code == 302
        assert '/payment' in res.headers['Location']
        db.session.expire_all()
        stored = db.session.get(Business, biz.id)
        assert stored.is_active is False
        assert stored.subscription_state == 'active'  # default, no dormant

    def test_biz_callback_bad_reference_redirects_payment(self, client, db):
        res = client.get('/payment-callback?status=approved'
                         '&external_reference=biz:xyz:crecimiento',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/payment' in res.headers['Location']

    def test_paid_plan_registration_goes_to_payment(self, client, app, db):
        """Registro con plan pago: sesión de pago lista y business inactivo
        hasta que MP confirme (callback/webhook)."""
        user = _mk_user(db, 'cb4@test.com')
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['selected_plan'] = 'emprendedor'

        token = _csrf_token(client, app)
        res = client.post('/register/verduras', data={
            'business_name': 'Verduras Pago',
            'whatsapp_phone': '+573001230004',
            'accept_terms': 'y',
            'csrf_token': token,
        }, follow_redirects=False)
        assert res.status_code == 302
        assert res.headers['Location'].endswith('/payment')

        biz = Business.query.filter_by(owner_user_id=user.id).first()
        assert biz.is_active is False
        with client.session_transaction() as sess:
            assert sess.get('pending_business_id') == biz.id
            assert sess.get('pos_setup_token')  # setup preservado para después

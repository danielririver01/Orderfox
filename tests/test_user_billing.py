"""
Tests de la Etapa 3 del Ecosistema Multi-Mundos: escrituras de billing
unificadas al User (fuente única) con sincronización de cachés legacy.

Cubren:
- activate_user_from_payment: un pago activa/extiende al DUEÑO y sincroniza
  todos sus mundos (restaurante + businesses); limpia dormant_at; es
  idempotente por mp_payment_id (marcador tx wallet, constraint único).
- start_user_trial: el trial es de la CUENTA (un solo reloj); no-op con
  ciclo activo o trial usado; alinea la caché de un mundo nuevo.
- Cancelación/resumen: propagan el estado de la cuenta a todas las cachés.
- Scheduler: _lifecycle_users pausa TODOS los mundos de una cuenta vencida;
  los caminos legacy por fila (restaurante/business sin dueño) siguen
  funcionando; los dueños activos no se tocan.
- Carriles de pago: _finalize_payment (restaurante) y
  activate_business_from_payment (biz) con dueño escriben al User; la regla
  de oro (fila sin dueño se gobierna sola) queda intacta.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models import AITokenTransaction, Business, Restaurant, User
from app.services.subscription_service import SubscriptionService
from app.services.user_billing import (
    activate_user_from_payment,
    owner_carries_billing,
    request_user_cancellation,
    resolve_owner,
    resume_user_subscription,
    start_user_trial,
)
from app.tasks import _lifecycle_users
from app.utils.subscription import GRACE_PERIOD_DAYS

_user_seq = iter(__import__('itertools').count(700))


def _dt(days):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _mk_user(db, email):
    user = User(username=f'Dueño {next(_user_seq)}', email=email,
                password='x-no-hash-needed')
    db.session.add(user)
    db.session.commit()
    return user


def _mk_owner_worlds(db, email, *, r_expires_in=30, r_state='active',
                     r_is_active=True, b_expires_in=30, b_state='active',
                     b_is_active=True, user_carries=True):
    """Dueño con restaurante vinculado + una verdulería propia.

    user_carries=True espeja el estado POST-migración: el dueño lleva su
    propio ciclo (backfill b6d8f0a2c4e6) y por tanto gobierna sus filas.
    user_carries=False = dueño recién creado sin billing (frontera legacy)."""
    seq = next(_user_seq)
    user = _mk_user(db, email)
    r = Restaurant(
        name=f'Rest {seq}', slug=f'rest-{seq}',
        whatsapp_phone='+573001112233', plan_type='emprendedor',
        subscription_state=r_state,
        subscription_expires_at=_dt(r_expires_in) if r_expires_in is not None else None,
        is_active=r_is_active,
    )
    db.session.add(r)
    db.session.flush()
    user.restaurant_id = r.id
    if user_carries:
        user.plan_type = 'emprendedor'
        user.subscription_state = r_state
        user.subscription_expires_at = (
            _dt(r_expires_in) if r_expires_in is not None else None)
    biz = Business.create_direct('verduras', f'Verdulas {seq}',
                                 f'verd-{seq}')
    biz.owner_user_id = user.id
    biz.plan_type = 'emprendedor'
    biz.subscription_state = b_state
    biz.subscription_expires_at = (
        _dt(b_expires_in) if b_expires_in is not None else None)
    biz.is_active = b_is_active
    db.session.commit()
    return user, r, biz


# ═════════════════ Pago a nivel User ═════════════════


class TestActivateUserFromPayment:
    def test_payment_activates_owner_and_all_worlds(self, app, db):
        user, r, biz = _mk_owner_worlds(
            db, 'pay1@test.com', r_expires_in=-40, r_state='dormant',
            r_is_active=False, b_expires_in=-40, b_state='dormant',
            b_is_active=False)
        with app.app_context():
            activate_user_from_payment(user, 'crecimiento', payment_id='pay-1')
            db.session.commit()

        db.session.expire_all()
        owner = db.session.get(User, user.id)
        assert owner.plan_type == 'crecimiento'
        assert owner.subscription_state == 'active'
        assert owner.subscription_expires_at > datetime.now(timezone.utc)

        rest = db.session.get(Restaurant, r.id)
        assert rest.plan_type == 'crecimiento'
        assert rest.subscription_state == 'active'
        assert rest.is_active is True
        assert rest.dormant_at is None

        stored = db.session.get(Business, biz.id)
        assert stored.plan_type == 'crecimiento'
        assert stored.subscription_state == 'active'
        assert stored.is_active is True
        assert stored.dormant_at is None

        assert AITokenTransaction.query.filter_by(
            mp_payment_id='pay-1', type='topup_plan').first() is not None

    def test_payment_idempotent_by_marker(self, app, db):
        user, _, _ = _mk_owner_worlds(db, 'pay2@test.com')
        with app.app_context():
            activate_user_from_payment(user, 'crecimiento',
                                       payment_id='pay-2')
            db.session.commit()
            db.session.expire_all()
            first = db.session.get(User, user.id).subscription_expires_at
            # Reintento (webhook después del callback): NO re-extiende.
            activate_user_from_payment(db.session.get(User, user.id),
                                       'crecimiento', payment_id='pay-2')
            db.session.expire_all()
            second = db.session.get(User, user.id).subscription_expires_at
        assert first == second

    def test_payment_extends_from_active_subscription(self, app, db):
        user, _, _ = _mk_owner_worlds(db, 'pay3@test.com', r_expires_in=10)
        with app.app_context():
            activate_user_from_payment(user, 'emprendedor',
                                       payment_id='pay-3')
            db.session.commit()
        db.session.expire_all()
        expires = db.session.get(User, user.id).subscription_expires_at
        remaining = (expires - datetime.now(timezone.utc)).days
        assert 39 <= remaining <= 41  # 10 vigentes + 30 del plan

    def test_none_owner_noop(self, app, db):
        with app.app_context():
            assert activate_user_from_payment(
                None, 'elite', payment_id='pay-4') is None


# ═════════════════ Trial de cuenta ═════════════════


class TestStartUserTrial:
    def test_trial_sets_owner_clock(self, app, db):
        user, _, _ = _mk_owner_worlds(
            db, 'tr1@test.com', r_expires_in=None, b_expires_in=None,
            user_carries=False)
        user.subscription_expires_at = None
        db.session.commit()
        with app.app_context():
            start_user_trial(db.session.get(User, user.id), days=60)
            db.session.commit()
        db.session.expire_all()
        owner = db.session.get(User, user.id)
        assert owner.plan_type == 'trial'
        assert owner.has_used_trial is True
        assert owner.subscription_expires_at > datetime.now(timezone.utc)

    def test_trial_noop_when_owner_has_active_cycle(self, app, db):
        user, _, biz = _mk_owner_worlds(db, 'tr2@test.com', r_expires_in=20)
        with app.app_context():
            start_user_trial(db.session.get(User, user.id), days=60)
            db.session.commit()
        db.session.expire_all()
        owner = db.session.get(User, user.id)
        assert owner.plan_type == 'emprendedor'  # no lo pisa el trial
        assert owner.has_used_trial is False
        # La caché de las filas se alinea al ciclo real del dueño.
        assert db.session.get(Business, biz.id).plan_type == 'emprendedor'

    def test_trial_noop_when_already_used(self, app, db):
        user, _, _ = _mk_owner_worlds(
            db, 'tr3@test.com', r_expires_in=None, b_expires_in=None,
            user_carries=False)
        user.has_used_trial = True
        db.session.commit()
        with app.app_context():
            start_user_trial(db.session.get(User, user.id), days=60)
            db.session.commit()
        db.session.expire_all()
        assert db.session.get(User, user.id).subscription_expires_at is None


# ═════════════════ Cancelación / reactivación ═════════════════


class TestCancellationPropagation:
    def test_cancel_and_resume_propagate_to_all_worlds(self, app, db):
        user, r, biz = _mk_owner_worlds(db, 'cx1@test.com')
        with app.app_context():
            owner = db.session.get(User, user.id)
            request_user_cancellation(owner)
            db.session.commit()
            db.session.expire_all()
            assert db.session.get(User, user.id).subscription_state == \
                'cancellation_pending'
            assert db.session.get(Restaurant, r.id).subscription_state == \
                'cancellation_pending'
            assert db.session.get(Business, biz.id).subscription_state == \
                'cancellation_pending'

            resume_user_subscription(db.session.get(User, user.id))
            db.session.commit()
            db.session.expire_all()
            assert db.session.get(User, user.id).subscription_state == 'active'
            assert db.session.get(Restaurant, r.id).subscription_state == \
                'active'
            assert db.session.get(Business, biz.id).subscription_state == \
                'active'

    def test_cancel_keeps_selling_until_date(self, app, db):
        """cancellation_pending NO apaga is_active: se sigue vendiendo
        hasta la expiración (misma semántica que restaurantes)."""
        user, r, _ = _mk_owner_worlds(db, 'cx2@test.com')
        with app.app_context():
            request_user_cancellation(db.session.get(User, user.id))
            db.session.commit()
        db.session.expire_all()
        assert db.session.get(Restaurant, r.id).is_active is True


# ═════════════════ Scheduler por User ═════════════════


class TestLifecycleUsers:
    def test_expired_owner_pauses_all_worlds(self, app, db):
        user, r, biz = _mk_owner_worlds(
            db, 'lc1@test.com', r_expires_in=-(GRACE_PERIOD_DAYS + 2),
            b_expires_in=-(GRACE_PERIOD_DAYS + 2))
        now = datetime.now(timezone.utc)
        with app.app_context():
            count = _lifecycle_users(now - timedelta(days=GRACE_PERIOD_DAYS),
                                     now)
        assert count >= 1
        db.session.expire_all()
        assert db.session.get(User, user.id).subscription_state == 'dormant'
        rest = db.session.get(Restaurant, r.id)
        assert rest.subscription_state == 'dormant'
        assert rest.is_active is False
        assert rest.dormant_at is not None
        stored = db.session.get(Business, biz.id)
        assert stored.subscription_state == 'dormant'
        assert stored.is_active is False
        assert stored.dormant_at is not None

    def test_active_owner_untouched(self, app, db):
        user, r, _ = _mk_owner_worlds(db, 'lc2@test.com', r_expires_in=20)
        now = datetime.now(timezone.utc)
        with app.app_context():
            _lifecycle_users(now - timedelta(days=GRACE_PERIOD_DAYS), now)
        db.session.expire_all()
        assert db.session.get(User, user.id).subscription_state == 'active'
        assert db.session.get(Restaurant, r.id).subscription_state == 'active'

    def test_owner_row_skipped_when_user_disabled(self, app, db):
        """User desactivado (suspensión manual) no entra al ciclo automático."""
        user, _, _ = _mk_owner_worlds(
            db, 'lc3@test.com', r_expires_in=-(GRACE_PERIOD_DAYS + 5))
        user.is_active = False
        db.session.commit()
        now = datetime.now(timezone.utc)
        with app.app_context():
            _lifecycle_users(now - timedelta(days=GRACE_PERIOD_DAYS), now)
        db.session.expire_all()
        assert db.session.get(User, user.id).subscription_state == 'active'

    def test_owner_carries_billing_frontier(self, app, db):
        """La frontera write == read: dueño sin ciclo propio NO gobierna
        (su fila se gestiona por el camino legacy); tras un pago, sí."""
        user, r, _ = _mk_owner_worlds(db, 'lc4@test.com', r_expires_in=-40,
                                      user_carries=False)
        assert owner_carries_billing(user) is False
        with app.app_context():
            activate_user_from_payment(user, 'emprendedor', payment_id='lc-4')
            db.session.commit()
        assert owner_carries_billing(db.session.get(User, user.id)) is True
        assert resolve_owner(db.session.get(Restaurant, r.id)) is not None


class TestPerformLifecycleEndToEnd:
    def test_expired_owner_account_pauses_everything(self, app, db):
        user, r, biz = _mk_owner_worlds(
            db, 'e2e1@test.com', r_expires_in=-(GRACE_PERIOD_DAYS + 3),
            b_expires_in=-(GRACE_PERIOD_DAYS + 3))
        from app.tasks import _perform_lifecycle
        with app.app_context():
            _perform_lifecycle()
        db.session.expire_all()
        assert db.session.get(User, user.id).subscription_state == 'dormant'
        assert db.session.get(Restaurant, r.id).subscription_state == 'dormant'
        assert db.session.get(Business, biz.id).subscription_state == 'dormant'
        # Y solo UNA pasada: no hay doble contabilidad de dormant_at.

    def test_ownerless_restaurant_row_path_intact(self, app, db):
        """Regla de oro: restaurante sin dueño corre su ciclo clásico."""
        r = Restaurant(name='Rest Legacy', slug='rest-legacy-e2e',
                       whatsapp_phone='+573009998877', is_active=True,
                       subscription_expires_at=_dt(-(GRACE_PERIOD_DAYS + 3)))
        db.session.add(r)
        db.session.commit()
        from app.tasks import _perform_lifecycle
        with app.app_context():
            _perform_lifecycle()
        db.session.expire_all()
        assert db.session.get(Restaurant, r.id).subscription_state == 'dormant'


# ═════════════════ Carriles de pago (restaurant y biz) ═════════════════


class TestPaymentLanes:
    def test_finalize_payment_with_owner_writes_user(self, app, db):
        user, r, _ = _mk_owner_worlds(
            db, 'lane1@test.com', r_expires_in=-40, r_state='dormant',
            r_is_active=False)
        with patch('app.services.subscription_service.'
                   '_deliver_sorpresa_velzia'), app.app_context():
            SubscriptionService._finalize_payment(
                db.session.get(Restaurant, r.id), 'crecimiento', 'lane-1')

        db.session.expire_all()
        owner = db.session.get(User, user.id)
        assert owner.plan_type == 'crecimiento'
        assert owner.subscription_state == 'active'
        rest = db.session.get(Restaurant, r.id)
        assert rest.subscription_state == 'active'
        assert rest.is_active is True
        assert rest.plan_type == 'crecimiento'
        assert AITokenTransaction.query.filter_by(
            mp_payment_id='lane-1', type='topup_plan').first() is not None

    def test_biz_payment_with_owner_activates_account(self, app, db):
        user, r, biz = _mk_owner_worlds(
            db, 'lane2@test.com', b_expires_in=None, b_state='dormant',
            b_is_active=False)
        with app.app_context():
            out = SubscriptionService.activate_business_from_payment(
                biz.id, 'emprendedor', 'lane-2')

        assert out is not None
        db.session.expire_all()
        owner = db.session.get(User, user.id)
        assert owner.plan_type == 'emprendedor'
        assert owner.subscription_state == 'active'
        stored = db.session.get(Business, biz.id)
        assert stored.is_active is True
        assert stored.subscription_state == 'active'
        assert stored.plan_type == 'emprendedor'
        # El pago de UN mundo activa la CUENTA: el restaurante también.
        assert db.session.get(Restaurant, r.id).is_active is True
        assert AITokenTransaction.query.filter_by(
            mp_payment_id='lane-2', type='topup_plan').first() is not None

    def test_biz_payment_legacy_without_owner_row_only(self, app, db):
        """Regla de oro: business sin dueño se activa en su propia fila."""
        biz = Business.create_direct('verduras', 'Verdulas Legacy',
                                     'verd-legacy-lane')
        biz.subscription_state = 'dormant'
        biz.is_active = False
        biz.subscription_expires_at = _dt(-40)
        db.session.commit()
        with app.app_context():
            out = SubscriptionService.activate_business_from_payment(
                biz.id, 'crecimiento', 'lane-3')
        db.session.expire_all()
        stored = db.session.get(Business, biz.id)
        assert out is not None
        assert stored.is_active is True
        assert stored.plan_type == 'crecimiento'
        assert stored.subscription_state == 'active'
        assert stored.subscription_expires_at is not None

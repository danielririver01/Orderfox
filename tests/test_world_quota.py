"""
Tests de la Etapa 4: bloqueo de activación de mundos según cupo del plan.

Cubren:
- can_activate_vertical: frontera exacta del cupo (trial=2, emprendedor=2,
  crecimiento=4, elite=∞) contando restaurante + businesses propios (los
  espejos NUNCA suman).
- vertical_quota_message: texto de upgrade claro para el flash.
- Servicio register_verduras_business: rechaza sin cupo (autoritativo).
- Rutas: /register/verduras y /setup-account redirigen a /planes con flash
  cuando el dueño está al límite; el flujo con cupo sigue funcionando.
"""
import pytest
from werkzeug.security import generate_password_hash

from app.models import Business, Restaurant, User
from app.services.business_registration import (
    BusinessRegistrationError,
    register_verduras_business,
)
from app.utils.subscription import can_activate_vertical, vertical_quota_message

_user_seq = iter(__import__('itertools').count(500))


def _mk_user(db, email, plan=None, expires_in=30):
    user = User(username=f'Dueño {next(_user_seq)}', email=email,
                password=generate_password_hash('Secreta1'))
    if plan:
        user.plan_type = plan
        from datetime import datetime, timedelta, timezone
        user.subscription_expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in))
    db.session.add(user)
    db.session.commit()
    return user


def _mk_verduras(db, user, name):
    seq = next(_user_seq)
    biz = Business.create_direct('verduras', name, f'verd-{seq}')
    biz.owner_user_id = user.id
    db.session.commit()
    return biz


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


# ═════════════════ Frontera del cupo ═════════════════


class TestCanActivateVertical:
    def test_first_world_always_ok(self, db):
        user = _mk_user(db, 'q1@test.com', plan='emprendedor')
        ok, info = can_activate_vertical(user)
        assert ok is True
        assert info['current_worlds'] == 0
        assert info['max_worlds'] == 2

    def test_trial_limit_is_two(self, db):
        user = _mk_user(db, 'q2@test.com', plan='trial')
        _mk_verduras(db, user, 'Verdulas Uno')
        r = Restaurant(name='Rest Q2', slug='rest-q2',
                       whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.flush()
        user.restaurant_id = r.id
        db.session.commit()
        # 2 mundos (restaurante + verdulería) → el tercero no cabe.
        ok, info = can_activate_vertical(user)
        assert ok is False
        assert info['current_worlds'] == 2
        assert info['max_worlds'] == 2

    def test_emprendedor_blocks_third_world(self, db):
        user = _mk_user(db, 'q3@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        _mk_verduras(db, user, 'Verdulas Dos')
        ok, info = can_activate_vertical(user)
        assert ok is False
        assert info['current_worlds'] == 2
        assert info['upgrade_to'] == 'Crecimiento'

    def test_emprendedor_allows_exactly_two(self, db):
        user = _mk_user(db, 'q4@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        ok, _ = can_activate_vertical(user)
        assert ok is True

    def test_crecimiento_allows_four(self, db):
        user = _mk_user(db, 'q5@test.com', plan='crecimiento')
        for i in range(3):
            _mk_verduras(db, user, f'Verdulas {i}')
        ok, info = can_activate_vertical(user)
        assert ok is True
        assert info['current_worlds'] == 3

    def test_crecimiento_blocks_fifth(self, db):
        user = _mk_user(db, 'q6@test.com', plan='crecimiento')
        r = Restaurant(name='Rest Q6', slug='rest-q6',
                       whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.flush()
        user.restaurant_id = r.id
        db.session.commit()
        for i in range(3):
            _mk_verduras(db, user, f'Verdulas {i}')
        # Restaurante + 3 verdulerías = 4 mundos (cupo lleno).
        ok, info = can_activate_vertical(user)
        assert ok is False
        assert info['current_worlds'] == 4
        assert info['upgrade_to'] == 'Élite'

    def test_elite_unlimited(self, db):
        user = _mk_user(db, 'q7@test.com', plan='elite')
        for i in range(6):
            _mk_verduras(db, user, f'Verdulas {i}')
        ok, info = can_activate_vertical(user)
        assert ok is True
        assert info['max_worlds'] is None

    def test_mirrors_never_count(self, db):
        """El espejo del restaurante NO suma: el mundo restaurante cuenta
        una sola vez (vía user.restaurant_id)."""
        user = _mk_user(db, 'q8@test.com', plan='emprendedor')
        r = Restaurant(name='Rest Q8', slug='rest-q8',
                       whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.flush()
        user.restaurant_id = r.id
        db.session.commit()
        # El listener del puente ya creó el espejo con owner_user_id
        # (columna de businesses); verificar que el conteo sigue en 1.
        assert Business.query.filter_by(vertical='restaurant').count() >= 1
        ok, info = can_activate_vertical(user)
        assert ok is True
        assert info['current_worlds'] == 1


# ═════════════════ Mensaje de upgrade ═════════════════


class TestQuotaMessage:
    def test_message_includes_plan_and_upgrade(self, db):
        user = _mk_user(db, 'm1@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        _mk_verduras(db, user, 'Verdulas Dos')
        _, info = can_activate_vertical(user)
        msg = vertical_quota_message(info)
        assert 'Emprendedor' in msg
        assert '2' in msg
        assert 'Crecimiento' in msg

    def test_message_without_upgrade_tier(self):
        msg = vertical_quota_message({'max_worlds': 2, 'current_worlds': 2,
                                      'plan_name': 'Emprendedor'})
        assert 'Emprendedor' in msg


# ═════════════════ Servicio (autoritativo) ═════════════════


class TestServiceQuotaEnforcement:
    def test_service_blocks_without_quota(self, db):
        user = _mk_user(db, 'sv1@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        _mk_verduras(db, user, 'Verdulas Dos')
        with pytest.raises(BusinessRegistrationError) as exc:
            register_verduras_business(
                user=user, business_name='Verdulas Tres',
                whatsapp_phone='+573001112233', selected_plan='trial')
        assert 'Emprendedor' in str(exc.value)
        assert 'Crecimiento' in str(exc.value)

    def test_service_allows_with_quota(self, db):
        user = _mk_user(db, 'sv2@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        biz, token = register_verduras_business(
            user=user, business_name='Verdulas Dos',
            whatsapp_phone='+573001112233', selected_plan='trial')
        assert biz is not None
        assert token
        assert biz.owner_user_id == user.id


# ═════════════════ Rutas (UX de upgrade) ═════════════════


class TestRouteQuotaGuards:
    def test_register_verduras_redirects_to_plans(self, client, app, db):
        user = _mk_user(db, 'rt1@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        _mk_verduras(db, user, 'Verdulas Dos')
        _login(client, user)
        resp = client.get('/register/verduras', follow_redirects=False)
        assert resp.status_code == 302
        assert '/planes' in resp.headers['Location']

    def test_register_verduras_ok_with_quota(self, client, app, db):
        user = _mk_user(db, 'rt2@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        _login(client, user)
        resp = client.get('/register/verduras', follow_redirects=False)
        assert resp.status_code == 200

    def test_setup_account_redirects_to_plans(self, client, app, db):
        user = _mk_user(db, 'rt3@test.com', plan='emprendedor')
        _mk_verduras(db, user, 'Verdulas Uno')
        _mk_verduras(db, user, 'Verdulas Dos')
        _login(client, user)
        resp = client.get('/setup-account', follow_redirects=False)
        assert resp.status_code == 302
        assert '/planes' in resp.headers['Location']

    def test_setup_account_ok_with_quota(self, client, app, db):
        user = _mk_user(db, 'rt4@test.com', plan='emprendedor')
        _login(client, user)
        resp = client.get('/setup-account', follow_redirects=False)
        assert resp.status_code == 200

    def test_retomar_pending_setup_survives_quota(self, client, app, db):
        """El guard NO debe romper la recuperación del enlace perdido:
        retomar un setup pendiente no crea mundos nuevos."""
        user = _mk_user(db, 'rt5@test.com', plan='emprendedor')
        biz = _mk_verduras(db, user, 'Verdulas Uno')
        _mk_verduras(db, user, 'Verdulas Dos')
        biz.pos_setup_token = 'token-pendiente'
        db.session.commit()
        _login(client, user)
        resp = client.get('/register/verduras', follow_redirects=False)
        # Al cupo lleno, el retomar manda a su pantalla de setup, no a planes.
        assert resp.status_code == 302
        assert '/register/verduras/ready' in resp.headers['Location']

"""
Tests del registro self-service de verticales directos (Semana 6).

Cubren:
- register_verduras_business: trial (60 días, TrialHistory, token de setup),
  plan pago (inactivo hasta pagar), trial único por email Y por teléfono.
- Slugs: reservados rechazados, unicidad incremental.
- Validaciones: teléfono, dueño con restaurante, plan inválido.
- Flujo web: página protegida por sesión, POST end-to-end, pantalla ready
  con el enlace de setup, token que viaja por sesión.
- Compatibilidad restaurantes: el flujo viejo NO cambia (anti-bucle incluido).
"""
import itertools

import pytest
from werkzeug.security import generate_password_hash

from app.models import Business, TrialHistory, User
from app.models.business import DIRECT_VERTICAL_ID_FLOOR
from app.services.business_registration import (
    BusinessRegistrationError,
    register_verduras_business,
)

_user_seq = itertools.count(1)


def _mk_user(db, email):
    user = User(username=f'Dueño {next(_user_seq)}', email=email,
                password=generate_password_hash('Secreta1'))
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


def _csrf_token(client, app):
    """Patrón del proyecto (test_account_deletion.py): token crudo en sesión
    + header firmado con el serializer de Flask-WTF."""
    from itsdangerous import URLSafeTimedSerializer
    raw = 'test-csrf-raw-token'
    with client.session_transaction() as sess:
        sess['csrf_token'] = raw
    ser = URLSafeTimedSerializer(app.secret_key, salt='wtf-csrf-token')
    return ser.dumps(raw)


# ═════════════════ Servicio de registro ═════════════════


class TestRegisterVerdurasService:
    def test_trial_creates_active_business_with_token(self, db):
        user = _mk_user(db, 'dueño1@test.com')
        biz, token = register_verduras_business(
            user, 'Verduras La Plaza', '+573001112233', 'trial')
        assert biz.vertical == 'verduras'
        assert biz.plan_type == 'trial'
        assert biz.owner_user_id == user.id
        assert biz.is_active is True
        assert biz.subscription_expires_at is not None
        assert biz.has_used_trial is True
        assert biz.pos_setup_token == token
        assert token  # token de setup emitido
        assert biz.id >= DIRECT_VERTICAL_ID_FLOOR

    def test_paid_plan_inactive_until_payment(self, db):
        user = _mk_user(db, 'dueño2@test.com')
        biz, _token = register_verduras_business(
            user, 'Verduras del Valle', '+573001112234', 'emprendedor')
        assert biz.plan_type == 'emprendedor'
        assert biz.is_active is False
        assert biz.subscription_expires_at is None
        assert biz.has_used_trial is False

    def test_trial_blocked_same_email(self, db):
        """El mismo dueño no puede pedir un segundo trial (otro negocio)."""
        user = _mk_user(db, 'dueño3@test.com')
        register_verduras_business(user, 'Verduras Uno', '+573001000001',
                                   'trial')
        with pytest.raises(BusinessRegistrationError, match='ya disfrutó'):
            register_verduras_business(user, 'Verduras Dos',
                                       '+573001000002', 'trial')

    def test_trial_blocked_same_phone_other_email(self, db):
        user = _mk_user(db, 'dueño5@test.com')
        register_verduras_business(user, 'Verduras Tres', '+573001000003',
                                   'trial')
        user2 = _mk_user(db, 'otro-email@test.com')
        with pytest.raises(BusinessRegistrationError, match='ya disfrutó'):
            register_verduras_business(user2, 'Verduras Cuatro',
                                       '+573001000003', 'trial')

    def test_paid_plan_does_not_consume_trial(self, db):
        user = _mk_user(db, 'dueño6@test.com')
        register_verduras_business(user, 'Verduras Cinco',
                                   '+573001000005', 'crecimiento')
        assert TrialHistory.query.filter_by(
            email='dueño6@test.com').count() == 0

    def test_reserved_slug_rejected(self, db):
        user = _mk_user(db, 'dueño7@test.com')
        with pytest.raises(BusinessRegistrationError, match='reservado'):
            register_verduras_business(user, 'Admin', '+573001000007',
                                       'trial')

    def test_invalid_phone_rejected(self, db):
        user = _mk_user(db, 'dueño8@test.com')
        with pytest.raises(BusinessRegistrationError, match='WhatsApp'):
            register_verduras_business(user, 'Verduras Ocho', 'hola',
                                       'trial')

    def test_owner_with_restaurant_rejected(self, db):
        from app.models import Restaurant
        restaurant = Restaurant(name='Rest Duo', slug='rest-duo-x',
                                whatsapp_phone='+573001112233')
        db.session.add(restaurant)
        db.session.flush()
        user = _mk_user(db, 'dueño9@test.com')
        user.restaurant_id = restaurant.id
        db.session.commit()
        with pytest.raises(BusinessRegistrationError, match='restaurante'):
            register_verduras_business(user, 'Verduras Nueve',
                                       '+573001000009', 'trial')

    def test_slug_uniqueness_on_same_name(self, db):
        user = _mk_user(db, 'dueño10@test.com')
        biz1, _ = register_verduras_business(user, 'Verduras Repetidas',
                                             '+573001000010', 'trial')
        user2 = _mk_user(db, 'dueño11@test.com')
        biz2, _ = register_verduras_business(user2, 'Verduras Repetidas',
                                             '+573001000011', 'emprendedor')
        assert biz1.slug != biz2.slug

    def test_invalid_plan_rejected(self, db):
        user = _mk_user(db, 'dueño12@test.com')
        with pytest.raises(BusinessRegistrationError, match='Plan inválido'):
            register_verduras_business(user, 'Verduras Doce',
                                       '+573001000012', 'diamante')


class TestCreateDirectVertical:
    def test_rejects_restaurant_vertical(self, db):
        with pytest.raises(ValueError, match='espejo'):
            Business.create_direct_vertical(
                vertical='restaurant', name='X', slug='x-x',
                owner_user_id=1)

    def test_restaurant_mirror_has_no_owner_change(self, db):
        """Los espejos de restaurantes siguen naciendo por listener y sin
        owner (su dueño es User.restaurant_id, como siempre)."""
        from app.models import Restaurant
        restaurant = Restaurant(name='Rest Espejo', slug='rest-espejo-x',
                                whatsapp_phone='+573001112233')
        db.session.add(restaurant)
        db.session.commit()
        mirror = Business.query.filter_by(id=restaurant.id).first()
        assert mirror is not None
        assert mirror.vertical == 'restaurant'
        assert mirror.owner_user_id is None
        assert mirror.plan_type == 'trial'  # default de la columna


# ═════════════════ Flujo web ═════════════════


class TestRegisterVerdurasFlow:
    def test_page_requires_login(self, client, db):
        res = client.get('/register/verduras', follow_redirects=False)
        assert res.status_code == 302
        assert '/register' in res.headers['Location']

    def test_end_to_end_trial_flow(self, client, app, db):
        user = _mk_user(db, 'flow@test.com')
        _login(client, user)

        res = client.get('/register/verduras')
        assert res.status_code == 200
        assert b'verduras' in res.data

        # El guard CSRF de core valida siempre: patrón del proyecto
        token = _csrf_token(client, app)
        res = client.post('/register/verduras', data={
            'business_name': 'Verduras El Flujo',
            'whatsapp_phone': '+573001230001',
            'accept_terms': 'y',
            'csrf_token': token,
        }, follow_redirects=False)
        assert res.status_code == 302
        assert '/register/verduras/ready/' in res.headers['Location']

        # Pantalla ready con el enlace de setup
        res = client.get(res.headers['Location'])
        assert res.status_code == 200
        assert b'/pos/setup/' in res.data
        assert b'Verduras El Flujo' not in res.data  # slug en el enlace

        # El token en DB coincide con el mostrado
        biz = Business.query.filter_by(owner_user_id=user.id).first()
        assert biz.pos_setup_token  # emitido
        assert biz.slug in res.data.decode()

    def test_ready_without_token_redirects(self, client, db):
        user = _mk_user(db, 'flow2@test.com')
        _login(client, user)
        res = client.get('/register/verduras/ready/algun-slug',
                         follow_redirects=False)
        assert res.status_code == 302


# ═════════════════ Compatibilidad con restaurantes ═════════════════


class TestRestaurantFlowUnchanged:
    def test_register_redirects_setup_for_new_user(self, client, db):
        """Usuario SIN restaurante ni business → setup de restaurante
        (comportamiento original intacto)."""
        user = _mk_user(db, 'rest@test.com')
        _login(client, user)
        res = client.get('/register', follow_redirects=False)
        assert res.status_code == 302
        assert 'setup-account' in res.headers['Location']

    def test_register_redirects_dashboard_for_verduras_owner(self, client,
                                                             db):
        """Dueño de verduras que vuelve a /register → dashboard (no al
        setup de restaurante; anti-bucle)."""
        user = _mk_user(db, 'verd@test.com')
        register_verduras_business(user, 'Verduras Anti Bucle',
                                   '+573001230002', 'trial')
        _login(client, user)
        res = client.get('/register', follow_redirects=False)
        assert res.status_code == 302
        assert res.headers['Location'].endswith('/dashboard/')

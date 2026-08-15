"""
Tests de las 3 correcciones de eliminación de cuenta (Bug 1-3).

Cubre:
- Bug 1: la ruta web /dashboard/delete-account responde success: True y el
  frontend redirige a /login.
- Bug 2: DELETE /v1/users/{clerk_id} se llama ANTES de borrar en DB; si Clerk
  falla NO se borra la DB (sin estado intermedio); 404 = éxito.
- Bug 3: sync_or_create_user no regala trial a correos con TrialHistory;
  create_restaurant_from_setup marca has_used_trial=True; el response de
  /api/sync-clerk distingue is_first_time.
"""
from datetime import datetime, timezone

from app.models import Restaurant, TrialHistory, User
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService

# ───────────── Bug 1: respuesta de la ruta web ─────────────

class TestDeleteAccountRoute:

    def test_web_route_returns_success_true(self, app, db, sample_restaurant, sample_user):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = sample_user.id
            sess['username'] = sample_user.username
            sess['clerk_id'] = 'user_test_123'

        # La ruta web exige CSRF (no está exenta como /api/*).
        # Patrón del proyecto (test_auth_setup_terms.py): token crudo en
        # sesión + header firmado con el mismo serializer que usa Flask-WTF.
        from flask import current_app
        from itsdangerous import URLSafeTimedSerializer

        raw = 'test-csrf-raw-token'
        with client.session_transaction() as sess:
            sess['csrf_token'] = raw
        ser = URLSafeTimedSerializer(current_app.secret_key, salt='wtf-csrf-token')

        resp = client.post(
            '/dashboard/delete-account',
            headers={'X-CSRFToken': ser.dumps(raw)},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'message' in data

        # La cuenta quedó borrada en DB
        assert Restaurant.query.get(sample_restaurant.id) is None


# ───────────── Bug 2: orden Clerk → DB ─────────────

class TestDeleteClerkUser:

    def test_delete_clerk_user_success(self, app, monkeypatch):
        """DELETE /v1/users/{id} con 200 → éxito."""
        class FakeResponse:
            status_code = 200
            text = '{}'

        def fake_delete(url, headers=None, timeout=None):
            assert url == 'https://api.clerk.com/v1/users/user_abc'
            assert headers['Authorization'].startswith('Bearer ')
            return FakeResponse()

        monkeypatch.setattr('requests.delete', fake_delete)
        ok, err = AuthService.delete_clerk_user('user_abc')
        assert ok is True
        assert err is None

    def test_delete_clerk_user_not_found_is_success(self, app, monkeypatch):
        """404 = el usuario ya no existía en Clerk → estado deseado, éxito."""
        class FakeResponse:
            status_code = 404
            text = '{}'

        monkeypatch.setattr('requests.delete', lambda *a, **k: FakeResponse())
        ok, err = AuthService.delete_clerk_user('user_gone')
        assert ok is True
        assert err is None

    def test_delete_clerk_user_server_error(self, app, monkeypatch):
        """500 → fallo real, NO se debe borrar la DB."""
        class FakeResponse:
            status_code = 500
            text = 'Internal error'

        monkeypatch.setattr('requests.delete', lambda *a, **k: FakeResponse())
        ok, err = AuthService.delete_clerk_user('user_bad')
        assert ok is False
        assert err is not None

    def test_delete_clerk_user_network_error(self, app, monkeypatch):
        """Excepción de red → fallo real."""
        def boom(*a, **k):
            raise ConnectionError('network down')

        monkeypatch.setattr('requests.delete', boom)
        ok, err = AuthService.delete_clerk_user('user_net')
        assert ok is False
        assert err is not None

    def test_delete_clerk_user_none(self, app):
        ok, err = AuthService.delete_clerk_user(None)
        assert ok is True
        assert err is None


class TestDeleteRestaurantOrder:

    def test_delete_restaurant_calls_clerk_first(self, app, db, sample_restaurant, monkeypatch):
        """Clerk se llama ANTES de borrar en DB (orden crítico)."""
        calls = []

        class FakeResponse:
            status_code = 200
            text = '{}'

        def fake_delete(url, headers=None, timeout=None):
            calls.append(url)
            # En el momento de la llamada a Clerk la DB aún tiene el restaurant
            assert Restaurant.query.get(sample_restaurant.id) is not None
            return FakeResponse()

        monkeypatch.setattr('requests.delete', fake_delete)
        ok, _result = DashboardService.delete_restaurant(
            sample_restaurant, clerk_id='user_abc'
        )
        assert ok is True
        assert len(calls) == 1
        assert 'user_abc' in calls[0]
        assert Restaurant.query.get(sample_restaurant.id) is None

    def test_delete_restaurant_clerk_failure_keeps_db(self, app, db, sample_restaurant, monkeypatch):
        """Si Clerk falla → NO se borra la DB (sin estado intermedio)."""
        class FakeResponse:
            status_code = 500
            text = 'boom'

        monkeypatch.setattr('requests.delete', lambda *a, **k: FakeResponse())
        ok, result = DashboardService.delete_restaurant(
            sample_restaurant, clerk_id='user_bad'
        )
        assert ok is False
        assert result.get('clerk_error') is True
        # La cuenta sigue viva en DB
        assert Restaurant.query.get(sample_restaurant.id) is not None

    def test_delete_restaurant_no_clerk_id(self, app, db, sample_restaurant, monkeypatch):
        """Sin clerk_id (cuenta no-Clerk) → se borra directo, sin llamada externa."""
        called = []
        monkeypatch.setattr(
            'requests.delete',
            lambda *a, **k: called.append(1) or type('R', (), {'status_code': 200, 'text': ''})()
        )
        ok, _ = DashboardService.delete_restaurant(sample_restaurant)
        assert ok is True
        assert called == []
        assert Restaurant.query.get(sample_restaurant.id) is None

    def test_delete_restaurant_preserves_trial_history(self, app, db, sample_restaurant, sample_user):
        """TrialHistory persiste después de eliminar la cuenta (Bug 3, paso 5)."""
        th = TrialHistory(email=sample_user.email, whatsapp_phone=sample_restaurant.whatsapp_phone)
        db.session.add(th)
        db.session.commit()
        th_id = th.id

        ok, _ = DashboardService.delete_restaurant(sample_restaurant)
        assert ok is True
        assert TrialHistory.query.get(th_id) is not None


# ───────────── Bug 3: trial no se resetea ─────────────

class TestSyncOrCreateUserTrialBlocked:

    def test_existing_trial_history_blocks_trial(self, app, db, sample_user):
        """Correo con TrialHistory → NO recibe trial, retorna TRIAL_ALREADY_USED."""
        db.session.add(TrialHistory(email='used@test.com', whatsapp_phone='+573000000001'))
        db.session.commit()

        user, is_new, plan = AuthService.sync_or_create_user('user_x', 'used@test.com', 'used')
        assert user is None
        assert is_new is False
        assert plan['error_code'] == 'TRIAL_ALREADY_USED'

    def test_fresh_email_gets_trial(self, app, db):
        """Correo sin historial → trial normal (comportamiento intacto)."""
        user, is_new, plan = AuthService.sync_or_create_user('user_y', 'fresh@test.com', 'fresh')
        assert user is not None
        assert is_new is True
        assert plan == 'trial'

    def test_pre_reg_paid_plan_not_blocked(self, app, db):
        """Correo con TrialHistory que eligió plan PAGO → se permite el plan pago."""
        from app.models import PreRegistration
        db.session.add(TrialHistory(email='paid@test.com', whatsapp_phone='+573000000002'))
        db.session.add(PreRegistration(email='paid@test.com', selected_plan='emprendedor'))
        db.session.commit()

        user, is_new, plan = AuthService.sync_or_create_user('user_z', 'paid@test.com', 'paid')
        assert user is not None
        assert is_new is True
        assert plan == 'emprendedor'


class TestCreateRestaurantTrialFlag:

    def test_trial_restaurant_marks_has_used_trial(self, app, db):
        """Crear restaurante trial → has_used_trial=True (antes quedaba False)."""
        user = User(
            restaurant_id=None, username='trialuser',
            email='trialflag@test.com',
            password='x'
        )
        db.session.add(user)
        db.session.commit()

        restaurant, err = AuthService.create_restaurant_from_setup(
            user=user, email=user.email, restaurant_name='Trial Flag',
            phone='+573000000003', selected_plan='trial'
        )
        assert err is None
        assert restaurant.plan_type == 'trial'
        assert restaurant.has_used_trial is True
        assert restaurant.subscription_expires_at > datetime.now(timezone.utc)

        # TrialHistory también se registró
        assert TrialHistory.query.filter_by(email=user.email).first() is not None

    def test_paid_restaurant_does_not_mark_trial(self, app, db):
        user = User(
            restaurant_id=None, username='paiduser',
            email='paidflag@test.com', password='x'
        )
        db.session.add(user)
        db.session.commit()

        restaurant, err = AuthService.create_restaurant_from_setup(
            user=user, email=user.email, restaurant_name='Paid Flag',
            phone='+573000000004', selected_plan='emprendedor'
        )
        assert err is None
        assert restaurant.has_used_trial is False


# ───────────── Verificación E2E (5 pasos obligatorios) ─────────────

class TestE2EAccountLifecycle:
    """Flujo completo sin intervención manual (Clerk mockeado):

    1. Crear cuenta nueva → recibe trial (restaurante trial + TrialHistory).
    2. Eliminar cuenta → response success: True (frontend redirige a /login),
       Clerk recibe DELETE, DB borrada.
    3. Re-registro del MISMO email → NO recibe trial, redirige a /planes.
    4. El usuario fue eliminado en Clerk (DELETE /v1/users/{id} llamado).
    5. TrialHistory persiste después de la eliminación.
    """

    @staticmethod
    def _csrf_headers(client):
        from flask import current_app
        from itsdangerous import URLSafeTimedSerializer

        raw = 'e2e-csrf-raw-token'
        with client.session_transaction() as s:
            s['csrf_token'] = raw
        ser = URLSafeTimedSerializer(current_app.secret_key, salt='wtf-csrf-token')
        return {'X-CSRFToken': ser.dumps(raw)}

    @staticmethod
    def _valid_payload(extra=None):
        data = {
            'admin_name': 'E2E Admin',
            'restaurant_name': 'E2E Restaurant',
            'phone': '573009990001',
            'password': 'Test1234pass',
            'confirm_password': 'Test1234pass',
        }
        if extra:
            data.update(extra)
        return data

    def test_full_lifecycle(self, app, db, monkeypatch):
        deleted_clerk_urls = []

        # Mock Clerk API: verificación (GET sessions + users) y borrado (DELETE).
        def fake_get(url, headers=None, timeout=None):
            class R:
                status_code = 200

                def json(self):
                    if '/sessions/' in url:
                        # La sesión DEBE devolver user_id (Clerk Session object).
                        # El patrón sess_X → user_X coincide con los clerk_id
                        # usados en este test (sess_e2e_1 → user_e2e_1).
                        session_id = url.rsplit('/', 1)[-1]
                        return {'status': 'active', 'user_id': 'user_' + session_id[len('sess_'):]}
                    return {
                        'primary_email_address_id': 'ema_1',
                        'email_addresses': [
                            {'id': 'ema_1', 'email_address': 'e2e@test.com'}
                        ],
                    }
            return R()

        def fake_delete(url, headers=None, timeout=None):
            deleted_clerk_urls.append(url)

            class R:
                status_code = 200
                text = '{}'
            return R()

        monkeypatch.setattr('requests.get', fake_get)
        monkeypatch.setattr('requests.delete', fake_delete)

        client = app.test_client()

        # ── Paso 1: crear cuenta nueva → recibe trial ──
        r1 = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_e2e_1',
            'email': 'e2e@test.com',
            'session_id': 'sess_e2e_1',
            'username': 'e2euser',
        })
        data1 = r1.get_json()
        assert r1.status_code == 200
        assert data1['success'] is True
        assert data1['is_new_user'] is True
        assert data1['is_first_time'] is True
        assert data1['trial_plan'] is True
        assert data1['redirect_url'] == '/setup-account'

        # Completa el setup → restaurante trial creado
        r_setup = client.post(
            '/setup-account',
            data=self._valid_payload({'accept_terms': 'y'}),
            headers=self._csrf_headers(client),
            follow_redirects=False,
        )
        assert r_setup.status_code == 302

        user = User.query.filter_by(email='e2e@test.com').first()
        assert user is not None
        restaurant = user.restaurant
        assert restaurant.plan_type == 'trial'
        assert restaurant.has_used_trial is True
        assert TrialHistory.query.filter_by(email='e2e@test.com').first() is not None

        # ── Paso 2: eliminar cuenta → success: True (→ /login) ──
        r_del = client.post('/dashboard/delete-account', headers=self._csrf_headers(client))
        data_del = r_del.get_json()
        assert r_del.status_code == 200
        assert data_del['success'] is True
        assert 'message' in data_del

        # ── Paso 4: el usuario fue eliminado en Clerk ──
        assert any('user_e2e_1' in u for u in deleted_clerk_urls), \
            f"DELETE a Clerk nunca se llamó: {deleted_clerk_urls}"

        # DB borrada (usuario + restaurante)
        assert User.query.filter_by(email='e2e@test.com').first() is None
        assert Restaurant.query.get(restaurant.id) is None

        # ── Paso 5: TrialHistory persiste tras la eliminación ──
        th = TrialHistory.query.filter_by(email='e2e@test.com').first()
        assert th is not None
        assert th.whatsapp_phone == '573009990001'

        # ── Paso 3: re-registro del MISMO email → NO trial, va a /planes ──
        r3 = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_e2e_2',
            'email': 'e2e@test.com',
            'session_id': 'sess_e2e_2',
            'username': 'e2euser',
        })
        data3 = r3.get_json()
        assert r3.status_code == 200
        assert data3['success'] is True
        assert data3['trial_blocked'] is True
        assert data3['redirect_url'] == '/planes'
        assert 'Ya usaste tu período de prueba gratuito' in data3['message']
        # No se creó un usuario local nuevo con trial
        assert User.query.filter_by(email='e2e@test.com').first() is None


# ───────────── Bug 1b: redirect post-eliminación apunta a /login que NO existe ─────────────
#
# Regresión detectada en producción: tras eliminar la cuenta, el frontend
# (subscription.js) redirigía a '/login' hardcodeado, pero auth.login vive en
# la raíz '/' (auth_bp no tiene url_prefix). El resultado era un 404.
# El fix: subscription.js usa window.VELZIA_LOGIN_URL = url_for('auth.login').

class TestLoginUrlAfterAccountDeletion:

    def test_auth_login_is_root_not_login(self, app):
        """La ruta de login real es '/' (raíz). url_for('auth.login') no debe
        generar '/login' porque esa ruta no existe en el blueprint auth."""
        with app.test_request_context():
            from flask import url_for
            login_url = url_for('auth.login')
        assert login_url == '/'

    def test_login_path_returns_404(self, app):
        """GET /login no existe → 404. Documenta por qué el redirect hardcodeado
        a '/login' rompía tras eliminar la cuenta."""
        client = app.test_client()
        resp = client.get('/login')
        assert resp.status_code == 404

    def test_subscription_js_does_not_hardcode_login(self, app):
        """subscription.js ya no contiene window.location.href = '/login'."""
        import pathlib
        js_path = pathlib.Path(app.root_path).parent / 'app' / 'static' / 'js' / 'subscription.js'
        content = js_path.read_text(encoding='utf-8')
        assert "location.href = '/login'" not in content
        assert 'window.VELZIA_LOGIN_URL' in content

    def test_subscription_template_exposes_login_url(self, app):
        """subscription.html expone la URL real de login al JS vía
        window.VELZIA_LOGIN_URL."""
        import pathlib
        tpl = pathlib.Path(app.root_path) / 'template' / 'dashboard' / 'subscription.html'
        content = tpl.read_text(encoding='utf-8')
        assert 'window.VELZIA_LOGIN_URL' in content


# ───────────── Bug: loop planes→register→login con plan de pago ─────────────
#
# Regresión detectada en producción: un correo que ya usó el trial no puede
# comprar NINGÚN plan de pago. sync_or_create_user lee el plan de
# PreRegistration (o 'trial' por defecto), pero /planes→/register?plan=X
# guarda el plan en session['selected_plan'] sin persistirlo. El sync volvía
# a 'trial' → TRIAL_ALREADY_USED → loop infinito.
# El fix: sync_clerk persiste session['selected_plan'] vía save_plan_selection
# antes de delegar al servicio (solo si es plan de pago, no trial).

class TestPaidPlanAfterTrialBlocked:

    @staticmethod
    def _mock_clerk_verify(monkeypatch):
        def fake_get(url, headers=None, timeout=None):
            class R:
                status_code = 200

                def json(self):
                    if '/sessions/' in url:
                        # La sesión DEBE devolver user_id (Clerk Session object).
                        # El patrón sess_X → user_X coincide con los clerk_id
                        # usados (sess_paidloop_1 → user_paidloop_1, ...).
                        session_id = url.rsplit('/', 1)[-1]
                        return {'status': 'active', 'user_id': 'user_' + session_id[len('sess_'):]}
                    return {
                        'primary_email_address_id': 'ema_1',
                        'email_addresses': [
                            {'id': 'ema_1', 'email_address': 'paidloop@test.com'}
                        ],
                    }
            return R()

        monkeypatch.setattr('requests.get', fake_get)

    def test_sync_clerk_persists_selected_plan_before_sync(self, app, db, monkeypatch):
        """sync-clerk con session['selected_plan']='emprendedor' + TrialHistory
        → NO TRIAL_ALREADY_USED, crea el usuario con plan de pago."""
        from app.models import PreRegistration
        self._mock_clerk_verify(monkeypatch)
        db.session.add(TrialHistory(email='paidloop@test.com', whatsapp_phone='+573000000004'))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['selected_plan'] = 'emprendedor'

        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_paidloop_1',
            'email': 'paidloop@test.com',
            'session_id': 'sess_paidloop_1',
            'username': 'paidloop',
        })
        data = r.get_json()
        assert r.status_code == 200
        assert data['success'] is True
        assert data.get('trial_blocked') is None or data.get('trial_blocked') is False
        assert data['is_new_user'] is True
        assert data['redirect_url'] == '/setup-account'
        # Plan de pago (no trial)
        assert data['trial_plan'] is False

        # El PreRegistration se creó y fue consumido por sync_or_create_user
        # (auth_service lo borra al crear la cuenta). El plan se usó: el
        # usuario no quedó bloqueado y session recuerda el plan elegido.
        assert PreRegistration.query.filter_by(email='paidloop@test.com').first() is None
        with client.session_transaction() as sess:
            assert sess.get('selected_plan') == 'emprendedor'

        # El usuario se creó (no bloqueado)
        assert User.query.filter_by(email='paidloop@test.com').first() is not None

    def test_sync_clerk_trial_selected_still_blocked(self, app, db, monkeypatch):
        """Con session['selected_plan']='trial' (o sin plan), el trial sigue
        bloqueado → TRIAL_ALREADY_USED. El fix no regala trial."""
        self._mock_clerk_verify(monkeypatch)
        db.session.add(TrialHistory(email='paidloop@test.com', whatsapp_phone='+573000000004'))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['selected_plan'] = 'trial'

        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_paidloop_2',
            'email': 'paidloop@test.com',
            'session_id': 'sess_paidloop_2',
            'username': 'paidloop',
        })
        data = r.get_json()
        assert data['success'] is True
        assert data.get('trial_blocked') is True
        assert data['redirect_url'] == '/planes'
        assert User.query.filter_by(email='paidloop@test.com').first() is None

    def test_save_plan_selection_accepts_crecimiento(self, app, db):
        """save_plan_selection valida los planes reales; 'crecimiento' debe
        ser aceptado (antes validaba 'premium' inexistente)."""
        result, error = AuthService.save_plan_selection('crec@test.com', 'crecimiento')
        assert error is None
        assert result is not None
        assert result.selected_plan == 'crecimiento'

    def test_plans_page_hides_trial_button_for_trial_blocked(self, app, db):
        """/planes con sesión Clerk (clerk_id, sin user_id) no muestra botón
        de prueba gratis y sí muestra logout."""
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['clerk_id'] = 'user_tb_1'
            sess['trial_blocked'] = True

        resp = client.get('/planes')
        html = resp.get_data(as_text=True)
        assert 'Comenzar prueba gratis' not in html
        assert 'Ya usaste tu prueba' in html
        assert 'Salir' in html


# ───────────── Seguridad: la sesión Clerk debe pertenecer al clerk_id ─────────────
#
# Hueco detectado: verify_clerk_session solo comprobaba que la sesión estuviera
# 'active', pero NO que la sesión perteneciera al clerk_id enviado. Un atacante
# con SU propia sesión Clerk activa podía enviar clerk_id + email de otra
# persona y secuestrar su cuenta local. La API de Clerk devuelve user_id en el
# objeto Session (GET /v1/sessions/{id}).

class TestSessionUserMismatchSecurity:

    @staticmethod
    def _mock_clerk_session_for(monkeypatch, session_owner_clerk_id, email):
        """Mock donde la sesión pertenece a session_owner (no a la víctima)."""
        def fake_get(url, headers=None, timeout=None):
            class R:
                status_code = 200

                def json(self):
                    if '/sessions/' in url:
                        return {'status': 'active', 'user_id': session_owner_clerk_id}
                    return {
                        'primary_email_address_id': 'ema_1',
                        'email_addresses': [{'id': 'ema_1', 'email_address': email}]
                    }
            return R()
        monkeypatch.setattr('requests.get', fake_get)

    def test_sync_rejects_session_not_owned_by_clerk_id(self, app, db, monkeypatch):
        """sync-clerk con una sesión de OTRA persona → rechazado (401), NO se
        crea usuario ni se inicia sesión local."""
        self._mock_clerk_session_for(
            monkeypatch,
            session_owner_clerk_id='user_attacker_1',
            email='victim@test.com',
        )

        client = app.test_client()
        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_victim_1',
            'email': 'victim@test.com',
            'session_id': 'sess_attacker_1',
            'username': 'victim',
        })
        data = r.get_json()
        assert r.status_code == 401
        assert data['success'] is False
        assert data['error_code'] == 'SESSION_USER_MISMATCH'
        # Ni usuario local creado ni sesión secuestrada
        assert User.query.filter_by(email='victim@test.com').first() is None
        with client.session_transaction() as sess:
            assert 'user_id' not in sess

    def test_sync_accepts_session_owned_by_clerk_id(self, app, db, monkeypatch):
        """Sesión que SÍ pertenece al clerk_id → flujo normal (sanity check)."""
        self._mock_clerk_session_for(
            monkeypatch,
            session_owner_clerk_id='user_owner_1',
            email='owner@test.com',
        )

        client = app.test_client()
        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_owner_1',
            'email': 'owner@test.com',
            'session_id': 'sess_owner_1',
            'username': 'owner',
        })
        data = r.get_json()
        assert r.status_code == 200
        assert data['success'] is True
        assert User.query.filter_by(email='owner@test.com').first() is not None


# ───────────── UX: login con cuenta sin restaurante no cae en dashboard ─────────────
#
# Regresión: con user_id en sesión pero SIN restaurante, GET / redirigía a
# /dashboard/ → require_active → flash "Tu cuenta no está asociada a ningún
# restaurante" (alerta confusa). Debe llevar al flujo correcto: /planes si ya
# usó el trial, /setup-account si tiene plan elegido o es cuenta nueva.

class TestLoginNoRestaurantRouting:

    def test_login_without_restaurant_trial_used_goes_planes(self, app, db):
        user = User(
            restaurant_id=None, username='norest2',
            email='norest2@test.com', password='x',
            clerk_id='user_norest2',
        )
        db.session.add(user)
        db.session.add(TrialHistory(email='norest2@test.com', whatsapp_phone='+573000000011'))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['username'] = 'norest2'

        resp = client.get('/', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/planes')

    def test_login_without_restaurant_with_plan_goes_setup(self, app, db):
        user = User(
            restaurant_id=None, username='withplan2',
            email='withplan2@test.com', password='x',
            clerk_id='user_withplan2',
        )
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['username'] = 'withplan2'
            sess['selected_plan'] = 'emprendedor'

        resp = client.get('/', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/setup-account')

    def test_login_with_restaurant_goes_dashboard(self, app, db, sample_restaurant, sample_user):
        """Con restaurante el comportamiento original se mantiene: / → dashboard."""
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = sample_user.id
            sess['username'] = sample_user.username

        resp = client.get('/', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/dashboard/')


# ───────────── UX: /planes muestra los flashes (trial usado) ─────────────

class TestPlansShowsFlash:

    @staticmethod
    def _mock_clerk_verify(monkeypatch):
        def fake_get(url, headers=None, timeout=None):
            class R:
                status_code = 200

                def json(self):
                    if '/sessions/' in url:
                        session_id = url.rsplit('/', 1)[-1]
                        return {'status': 'active', 'user_id': 'user_' + session_id[len('sess_'):]}
                    return {
                        'primary_email_address_id': 'ema_1',
                        'email_addresses': [{'id': 'ema_1', 'email_address': 'flashtest@test.com'}]
                    }
            return R()
        monkeypatch.setattr('requests.get', fake_get)

    def test_planes_renders_flash_after_sync_trial_blocked(self, app, db, monkeypatch):
        """Flujo real: sync-clerk con trial usado + sin plan deja el flash y
        /planes lo renderiza (antes quedaba pendiente y aparecía fuera de
        contexto en register_verify)."""
        self._mock_clerk_verify(monkeypatch)
        user = User(
            restaurant_id=None, username='flashtest',
            email='flashtest@test.com', password='x',
            clerk_id='user_flashtest',
        )
        db.session.add(user)
        db.session.add(TrialHistory(email='flashtest@test.com', whatsapp_phone='+573000000012'))
        db.session.commit()

        client = app.test_client()
        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_flashtest',
            'email': 'flashtest@test.com',
            'session_id': 'sess_flashtest',
            'username': 'flashtest',
        })
        data = r.get_json()
        assert data['redirect_url'] == '/planes'

        resp = client.get('/planes')
        html = resp.get_data(as_text=True)
        assert 'Ya usaste tu período de prueba gratuito' in html


# ───────────── Bug: "secuestro" de sesión Clerk en /login y /setup-account ─────────────
#
# Regresión detectada en producción: con una sesión Clerk activa, el login (/) hacía
# sync silencioso automático (auth_index.js) sin opción de cambiar de cuenta, y
# /setup-account no ofrecía salida alguna. El resultado: el usuario quedaba
# atrapado en el flujo (no podía elegir otra cuenta ni abandonar el setup).
# El fix:
#  - auth_index.js: si existe sesión Clerk, muestra la tarjeta "Continuar como"
#    con botones [Continuar] (sync) y [Usar otra cuenta] (Clerk.signOut + reload).
#  - register_setup.html: cabecera con enlaces "Salir" y "Usar otra cuenta" que
#    enrutan por /logout (limpia session Flask + signOut Clerk + vuelve al login).

class TestSessionEscape:

    def test_login_js_shows_continue_card(self, app):
        """auth_index.js con sesión Clerk muestra la tarjeta 'Continuar como' en
        vez de sincronizar automáticamente."""
        import pathlib
        js_path = pathlib.Path(app.root_path).parent / 'app' / 'static' / 'js' / 'auth_index.js'
        content = js_path.read_text(encoding='utf-8')
        assert 'showContinueCard' in content
        assert 'Continuar como' in content
        assert 'Cerrar sesión' in content
        # Ya no existe el auto-sync incondicional que secuestraba la sesión
        assert 'window.Clerk.user && !hasFlashMessages' not in content

    def test_setup_account_has_escape_links(self, app):
        """register_setup.html ofrece la salida 'Cerrar sesión' enrutada por
        /logout (nadie queda atrapado en el setup)."""
        import pathlib
        tpl = pathlib.Path(app.root_path) / 'template' / 'auth' / 'register_setup.html'
        content = tpl.read_text(encoding='utf-8')
        assert 'Cerrar sesión' in content
        assert "url_for('auth.logout')" in content

    def test_logout_route_clears_session(self, app, db, sample_user):
        """GET /logout limpia session['user_id'] y devuelve la plantilla de cierre
        (que hace Clerk.signOut y redirige al login)."""
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = sample_user.id
            sess['username'] = sample_user.username
            sess['clerk_id'] = 'user_esc_1'

        resp = client.get('/logout')
        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert 'user_id' not in sess
            assert 'clerk_id' not in sess
        assert 'Cerrando tu sesión' in resp.get_data(as_text=True)


# ───────────── Bug: usuario EXISTENTE sin restaurante + trial usado ─────────────
#
# Regresión detectada en producción: dr4140485@gmail.com ya tiene cuenta local
# (users id 5, sin restaurant_id), ya usó el trial (TrialHistory) y no tiene
# PreRegistration. Al sincronizar con Clerk, sync_clerk lo trataba como usuario
# existente SIN plan y lo mandaba a /setup-account con plan=None. El template
# register_setup.html caía al else → mostraba "elite $50.000/mes" y "Continuar
# al Pago" sin haber elegido nada. Además /planes redirigía a setup-account a
# cualquier usuario con user_id sin restaurante, impidiendo elegir plan.
# El fix:
#  - sync_clerk: usuario existente sin restaurante y sin selected_plan que ya
#    usó trial → redirige a /planes (NO a setup-account).
#  - /planes: solo redirige a setup-account si el usuario NO usó trial.
#  - /setup-account: defensivo, redirige a /planes si llega sin plan y usó trial.

class TestExistingUserNoRestaurantTrialUsed:

    @staticmethod
    def _mock_clerk_verify(monkeypatch, email='existing@test.com'):
        def fake_get(url, headers=None, timeout=None):
            class R:
                status_code = 200

                def json(self):
                    if '/sessions/' in url:
                        # La sesión DEBE devolver user_id (Clerk Session object).
                        # El patrón sess_X → user_X coincide con los clerk_id
                        # usados (sess_existing_1 → user_existing_1, ...).
                        session_id = url.rsplit('/', 1)[-1]
                        return {'status': 'active', 'user_id': 'user_' + session_id[len('sess_'):]}
                    return {
                        'primary_email_address_id': 'ema_1',
                        'email_addresses': [
                            {'id': 'ema_1', 'email_address': email}
                        ],
                    }
            return R()

        monkeypatch.setattr('requests.get', fake_get)

    def test_sync_existing_user_trial_used_redirects_planes(self, app, db, monkeypatch):
        """Usuario existente sin restaurante + trial usado + sin plan → sync
        manda a /planes, NO a setup-account con plan=None."""
        self._mock_clerk_verify(monkeypatch)
        user = User(
            restaurant_id=None, username='existing',
            email='existing@test.com', password='x',
            clerk_id='user_existing_1',
        )
        db.session.add(user)
        db.session.add(TrialHistory(email='existing@test.com', whatsapp_phone='+573000000007'))
        db.session.commit()

        client = app.test_client()
        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_existing_1',
            'email': 'existing@test.com',
            'session_id': 'sess_existing_1',
            'username': 'existing',
        })
        data = r.get_json()
        assert r.status_code == 200
        assert data['success'] is True
        assert data['redirect_url'] == '/planes'
        with client.session_transaction() as sess:
            assert sess.get('trial_blocked') is True

    def test_sync_existing_user_no_trial_goes_setup_with_trial(self, app, db, monkeypatch):
        """Usuario existente sin restaurante que NO usó trial → setup-account
        con plan trial (comportamiento original intacto)."""
        self._mock_clerk_verify(monkeypatch, email='fresh@test.com')
        user = User(
            restaurant_id=None, username='fresh',
            email='fresh@test.com', password='x',
            clerk_id='user_fresh_1',
        )
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_fresh_1',
            'email': 'fresh@test.com',
            'session_id': 'sess_fresh_1',
            'username': 'fresh',
        })
        data = r.get_json()
        assert data['redirect_url'] == '/setup-account'
        with client.session_transaction() as sess:
            assert sess.get('selected_plan') == 'trial'

    def test_planes_shows_plans_for_existing_user_trial_used(self, app, db):
        """/planes con user_id en sesión + trial usado NO redirige a
        setup-account: permite ver y elegir plan."""
        user = User(
            restaurant_id=None, username='plansuser',
            email='plansuser@test.com', password='x',
            clerk_id='user_plans_1',
        )
        db.session.add(user)
        db.session.add(TrialHistory(email='plansuser@test.com', whatsapp_phone='+573000000008'))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['trial_blocked'] = True

        resp = client.get('/planes')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Emprendedor' in html
        assert 'Ya usaste tu prueba' in html

    def test_setup_account_redirects_planes_when_no_plan_and_trial_used(self, app, db):
        """GET /setup-account con user_id sin restaurante + trial usado + sin
        selected_plan → redirige a /planes (no renderiza plan=None)."""
        user = User(
            restaurant_id=None, username='setupuser',
            email='setupuser@test.com', password='x',
            clerk_id='user_setup_1',
        )
        db.session.add(user)
        db.session.add(TrialHistory(email='setupuser@test.com', whatsapp_phone='+573000000009'))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/setup-account')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/planes')

    def test_planes_uses_register_not_renew_without_restaurant(self, app, db):
        """Un usuario con user_id pero SIN restaurante debe ver los planes y el
        botón de plan pago debe ir a /register (compra nueva), NO a /renew
        (que exige restaurante y caía en dashboard.index → 404)."""
        user = User(
            restaurant_id=None, username='norest',
            email='norest@test.com', password='x',
            clerk_id='user_norest_1',
        )
        db.session.add(user)
        db.session.add(TrialHistory(email='norest@test.com', whatsapp_phone='+573000000010'))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/planes')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Botón de plan pago → register (no renew)
        assert "/register?plan=emprendedor" in html
        assert "/renew" not in html

    def test_sync_existing_user_with_plan_goes_setup(self, app, db, monkeypatch):
        """Usuario existente sin restaurante que ya eligió plan (selected_plan en
        sesión) → sync manda a setup-account con ese plan, no a /planes ni a
        dashboard.index (404)."""
        self._mock_clerk_verify(monkeypatch, email='withplan@test.com')
        user = User(
            restaurant_id=None, username='withplan',
            email='withplan@test.com', password='x',
            clerk_id='user_withplan_1',
        )
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['selected_plan'] = 'emprendedor'

        r = client.post('/api/sync-clerk', json={
            'clerk_id': 'user_withplan_1',
            'email': 'withplan@test.com',
            'session_id': 'sess_withplan_1',
            'username': 'withplan',
        })
        data = r.get_json()
        assert data['redirect_url'] == '/setup-account'


# ───────────── Webhook legacy MP: fail-closed ─────────────
#
# Antes: solo verificaba la firma SI MP_WEBHOOK_SECRET estaba configurado;
# si no lo estaba, procesaba igual (fail-open). Ahora es fail-closed como el
# webhook nuevo (/api/v1/webhooks/mercadopago): sin secret → 503, y con
# secret, la firma es obligatoria → 401 si no coincide.

class TestLegacyWebhookFailClosed:

    def test_no_secret_rejects_503(self, app, db):
        """Sin MP_WEBHOOK_SECRET configurado → 503 webhook_not_configured, no
        procesa nada (fail-closed)."""
        app.config['MP_WEBHOOK_SECRET'] = None
        client = app.test_client()
        resp = client.post('/webhook', json={'type': 'payment', 'data': {'id': '12345'}})
        data = resp.get_json()
        assert resp.status_code == 503
        assert data['success'] is False
        assert data['error'] == 'webhook_not_configured'

    def test_invalid_signature_rejects_401(self, app, db):
        """Con secret configurado pero firma ausente/incorrecta → 401, no
        procesa nada."""
        app.config['MP_WEBHOOK_SECRET'] = 'test-webhook-secret'
        client = app.test_client()
        resp = client.post('/webhook', json={'type': 'payment', 'data': {'id': '12345'}})
        data = resp.get_json()
        assert resp.status_code == 401
        assert data['success'] is False
        assert data['error'] == 'invalid_signature'

    def test_valid_signature_processes(self, app, db, monkeypatch):
        """Firma HMAC correcta → pasa a procesamiento (sanity check)."""
        import hmac as hmac_mod
        import hashlib
        from datetime import datetime, timezone

        app.config['MP_WEBHOOK_SECRET'] = 'test-webhook-secret'

        # Mock de la verificación real del pago (evita llamar a MP)
        def fake_process(payment_id, access_token):
            return {'restaurant_id': 1, 'plan_type': 'emprendedor'}
        monkeypatch.setattr(
            'app.routes.auth.SubscriptionService.process_mp_webhook_payment',
            fake_process,
        )

        payment_id = '98765'
        ts = '1700000000'
        message = f"{payment_id}.{ts}.test-webhook-secret"
        v1 = hmac_mod.new(
            b'test-webhook-secret',
            message.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        client = app.test_client()
        resp = client.post(
            '/webhook',
            json={'type': 'payment', 'data': {'id': payment_id}},
            headers={'x-signature': f'ts={ts},v1={v1}'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

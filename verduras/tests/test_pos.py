"""
Tests del POS del tendero (dashboard Jinja2 + sesión).

Cubren:
- Auth por PIN: setup server-to-server (x-api-key), login slug+PIN,
  lockout por intentos, logout, sesión expirada.
- Segregación de claves: el x-api-key NO da sesión de tendero.
- Venta walk-in por sesión: sin x-api-key, precio del catálogo,
  errores limpios (404 producto ajeno, 400 validación).
- CSRF del dashboard: el guard activo rechaza POST sin token.
"""
import re
from types import SimpleNamespace

import pytest

from app.models import Business
from verduras.services.catalog import create_category, create_product
from verduras.services.pos_auth import MAX_ATTEMPTS, setup_pos_pin

API_KEY = 'test-service-api-key'
AUTH = {'x-api-key': API_KEY}


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'pos-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras El Punto', slug=_slug())


@pytest.fixture()
def catalog_row(db, biz):
    cat = create_category(biz.id, 'Hortalizas')
    tomate = create_product(biz.id, cat.id, 'Tomate', 'kg', '3200.00')
    banano = create_product(biz.id, cat.id, 'Banano', 'unidad', '500.00')
    return SimpleNamespace(cat=cat, tomate=tomate, banano=banano)


def _set_pin(biz, pin='4321'):
    setup_pos_pin(biz.id, pin)


def _login(client, biz, pin='4321'):
    return client.post('/pos/login', data={'slug': biz.slug, 'pin': pin})


# ═════════════════ Setup del PIN (server-to-server) ═════════════════


class TestPosPinSetup:
    def test_setup_requires_api_key(self, client, db, biz):
        res = client.post(f'/api/verduras/businesses/{biz.id}/pos-pin',
                          json={'pin': '4321'})
        assert res.status_code == 401

    def test_setup_ok_and_login_flow(self, client, db, biz, catalog_row):
        res = client.post(f'/api/verduras/businesses/{biz.id}/pos-pin',
                          headers=AUTH, json={'pin': '4321'})
        assert res.status_code == 200

        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '4321'})
        assert res.status_code == 302
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert biz.name.encode() in res.data

    def test_setup_rejects_bad_pin(self, client, db, biz):
        res = client.post(f'/api/verduras/businesses/{biz.id}/pos-pin',
                          headers=AUTH, json={'pin': '12'})
        assert res.status_code == 400

    def test_setup_rejects_restaurant_mirror(self, client, db):
        from app.models import Restaurant
        r = Restaurant(name='Rest POS', slug=_slug(),
                       whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.flush()
        res = client.post(f'/api/verduras/businesses/{r.id}/pos-pin',
                          headers=AUTH, json={'pin': '4321'})
        assert res.status_code == 400


# ═════════════════ Login / sesión ═════════════════


class TestPosLogin:
    def test_login_wrong_pin_401_with_flash(self, client, db, biz):
        _set_pin(biz)
        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '9999'})
        assert res.status_code == 401
        assert b'incorrecto' in res.data

    def test_login_unknown_slug_same_generic_message(self, client, db, biz):
        _set_pin(biz)
        res = client.post('/pos/login',
                          data={'slug': 'no-existe', 'pin': '4321'})
        assert res.status_code == 401
        assert b'incorrecto' in res.data

    def test_login_without_pin_configured(self, client, db, biz):
        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '4321'})
        assert res.status_code == 401
        assert 'aún no configura'.encode() in res.data

    def test_lockout_after_max_attempts(self, client, db, biz):
        _set_pin(biz, '4321')
        for _ in range(MAX_ATTEMPTS):
            client.post('/pos/login',
                        data={'slug': biz.slug, 'pin': '0000'})
        # Intento con el PIN CORRECTO tras el lock → rechazado igual.
        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '4321'})
        assert res.status_code == 401
        assert b'Demasiados intentos' in res.data

    def test_login_success_redirects_to_pos(self, client, db, biz):
        _set_pin(biz)
        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '4321'},
                          follow_redirects=False)
        assert res.status_code == 302

    def test_logout_kills_session(self, client, db, biz, catalog_row):
        _set_pin(biz)
        _login(client, biz)
        client.post('/pos/logout')
        res = client.get(f'/pos/{biz.slug}', follow_redirects=False)
        assert res.status_code == 302  # de vuelta al login


# ═════════════════ Segregación de claves ═════════════════


class TestSessionKeySegregation:
    def test_api_key_does_not_grant_pos_session(self, client, db, biz,
                                                catalog_row):
        res = client.get(f'/pos/{biz.slug}', headers=AUTH,
                         follow_redirects=False)
        assert res.status_code == 302  # la key no sirve para el POS

    def test_pos_sell_rejects_without_session(self, client, db, biz,
                                              catalog_row):
        res = client.post(
            f'/pos/{biz.slug}/sell',
            json={'items': [{'product_id': catalog_row.tomate.id,
                             'quantity': '1'}]})
        assert res.status_code == 401


# ═════════════════ Venta por sesión ═════════════════


class TestPosSell:
    def _login_client(self, client, biz):
        _set_pin(biz)
        _login(client, biz)

    def test_sell_by_session(self, client, db, biz, catalog_row):
        self._login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/sell', json={
            'items': [{'product_id': catalog_row.tomate.id,
                       'quantity': '0.500'}]})
        assert res.status_code == 200
        data = res.get_json()['data']
        assert data['total'] == '$1.600,00'  # es-CO: punto miles, coma decimal
        assert data['sale_number'].startswith('V-')

    def test_sell_price_from_catalog_never_client(self, client, db, biz,
                                                  catalog_row):
        self._login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/sell', json={
            'items': [{'product_id': catalog_row.tomate.id, 'quantity': '1',
                       'price': '1'}]})
        assert res.get_json()['data']['total'] == '$3.200,00'

    def test_sell_foreign_product_404(self, client, db, biz, catalog_row):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        cat2 = create_category(other.id, 'Otras')
        prod2 = create_product(other.id, cat2.id, 'Zanahoria', 'kg', '1000')
        self._login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/sell', json={
            'items': [{'product_id': prod2.id, 'quantity': '1'}]})
        assert res.status_code == 404

    def test_sell_slug_mismatch_rejected(self, client, db, biz, catalog_row):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro2', slug=_slug())
        _set_pin(other)
        self._login_client(client, biz)
        res = client.post(f'/pos/{other.slug}/sell', json={'items': []})
        assert res.status_code == 401

    def test_sell_validation_error_400(self, client, db, biz, catalog_row):
        self._login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/sell', json={'items': []})
        assert res.status_code == 400


# ═════════════════ Pantalla del POS ═════════════════


class TestPosView:
    def test_pos_view_renders_products_and_data(self, client, db, biz,
                                                catalog_row):
        _set_pin(biz)
        _login(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert b'Tomate' in res.data
        assert b'pos-data' in res.data  # JSON que alimenta el carrito
        assert b'csrf-token' in res.data

    def test_pos_view_without_session_redirects(self, client, db, biz):
        res = client.get(f'/pos/{biz.slug}', follow_redirects=False)
        assert res.status_code == 302

    def test_pos_home_redirects_by_session_state(self, client, db, biz):
        res = client.get('/pos', follow_redirects=False)
        assert res.status_code == 302  # sin sesión → login

        _set_pin(biz)
        _login(client, biz)
        res = client.get('/pos', follow_redirects=False)
        assert res.status_code == 302
        assert f'/pos/{biz.slug}'.encode() in res.data  # con sesión → POS


# ═════════════════ CSRF del dashboard ═════════════════


class TestCsrfGuard:
    def test_dashboard_post_requires_csrf_when_enabled(self, app, db, biz,
                                                       catalog_row):
        _set_pin(biz)
        app.config['WTF_CSRF_ENABLED'] = True
        try:
            client = app.test_client()
            # POST sin token → 400 del guard
            res = client.post('/pos/login',
                              data={'slug': biz.slug, 'pin': '4321'})
            assert res.status_code == 400

            # Con el token del formulario → login normal
            html = client.get('/pos/login').data.decode()
            match = re.search(
                r'name="csrf_token"[^>]*value="([^"]+)"', html)
            assert match, 'el template debe incluir csrf_token'
            res = client.post('/pos/login', data={
                'slug': biz.slug, 'pin': '4321',
                'csrf_token': match.group(1)})
            assert res.status_code == 302
        finally:
            app.config['WTF_CSRF_ENABLED'] = False

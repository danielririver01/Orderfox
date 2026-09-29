"""
Configuración v1: ajustes honestos (Tier GUARDIAN — acceso y PIN).

Cubre: página con las 4 tarjetas, guardar negocio, cambio de PIN con el
actual (incorrecto → 401), guards de sesión y slug ajeno.
"""
import pytest

from app.models import Business


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'cfg-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras Config', slug=_slug())


def _login_client(client, biz, pin='4321'):
    from verduras.services.pos_auth import setup_pos_pin
    setup_pos_pin(biz.id, pin)
    return client.post('/pos/login', data={'slug': biz.slug, 'pin': pin})


class TestPosConfig:
    def test_page_renders_four_cards(self, client, db, biz):
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/config')
        html = res.get_data(as_text=True)
        assert res.status_code == 200
        for text in ('El negocio', 'PIN del mostrador', 'Balanza',
                     'Suscripción', 'Gestionar en panel'):
            assert text in html

    def test_requires_session(self, client, db, biz):
        res = client.get(f'/pos/{biz.slug}/config',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_save_negocio_persists(self, client, db, biz):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/config/negocio', json={
            'whatsapp_phone': '+573001112233', 'is_open': False})
        assert res.status_code == 200
        assert res.get_json()['data']['is_open'] is False
        db.session.expire_all()
        from verduras.services.sales import get_settings
        # El servicio normaliza (solo dígitos con código de país).
        assert get_settings(biz.id).whatsapp_phone == '573001112233'

    def test_pin_change_needs_current(self, client, db, biz):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/config/pin', json={
            'current_pin': '0000', 'new_pin': '9999', 'new_pin2': '9999'})
        assert res.status_code == 401
        res = client.post(f'/pos/{biz.slug}/config/pin', json={
            'current_pin': '4321', 'new_pin': '9999', 'new_pin2': '9999'})
        assert res.status_code == 200
        # El nuevo PIN abre sesión (logout implícito vía sesión fresca).
        c2 = biz  # noqa: F841
        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '9999'})
        assert res.status_code == 302

    def test_foreign_slug_rejected(self, client, db, biz):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        _login_client(client, biz)
        res = client.post(f'/pos/{other.slug}/config/negocio',
                          json={'whatsapp_phone': '+57300', 'is_open': True})
        assert res.status_code == 401

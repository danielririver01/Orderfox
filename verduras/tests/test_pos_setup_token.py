"""
Tests del setup del POS con token de un solo uso (Semana 6 / v0.8.0).

Flujo self-service: core registra el negocio y deja el token en
`businesses.pos_setup_token` (DB compartida); el dueño abre
/pos/setup/<slug>/<token>, elige PIN (+ WhatsApp) y el enlace muere.

Cubren:
- get_setup_target: token válido, inválido y ya usado.
- consume_setup_token: PIN hasheado, WhatsApp en settings del módulo,
  token limpiado (un solo uso), login inmediato después.
- Rutas: GET con token válido/inválido, POST completo end-to-end.
- Validación de PIN débil rechazada SIN consumir el token.
"""
import pytest

from app.models import Business
from verduras.services.pos_auth import (
    PosAuthError,
    consume_setup_token,
    get_setup_target,
    has_pos_pin,
    login_pos,
)


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'setup-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    business = Business.create_direct(vertical='verduras',
                                      name='Verduras Setup', slug=_slug())
    business.pos_setup_token = 'token-secreto-123'
    db.session.commit()
    return business


# ═════════════════ get_setup_target ═════════════════


class TestGetSetupTarget:
    def test_valid_token_returns_business(self, db, biz):
        assert get_setup_target(biz.slug, 'token-secreto-123').id == biz.id

    def test_invalid_token_raises(self, db, biz):
        with pytest.raises(PosAuthError, match='no es válido'):
            get_setup_target(biz.slug, 'otro-token')

    def test_unknown_slug_raises(self, db, biz):
        with pytest.raises(PosAuthError, match='no es válido'):
            get_setup_target('no-existe', 'token-secreto-123')

    def test_restaurant_mirror_rejected(self, db):
        from app.models import Restaurant
        r = Restaurant(name='Rest Setup', slug=_slug(),
                       whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.commit()
        with pytest.raises(PosAuthError, match='no es válido'):
            get_setup_target(r.slug, 'lo-que-sea')


# ═════════════════ consume_setup_token ═════════════════


class TestConsumeSetupToken:
    def test_sets_pin_whatsapp_and_clears_token(self, db, biz):
        consume_setup_token(biz.slug, 'token-secreto-123', '4321',
                            whatsapp_phone='+573001555000')
        assert has_pos_pin(biz.id) is True
        assert biz.pos_setup_token is None  # un solo uso
        from verduras.services.sales import get_settings
        # El teléfono queda en formato limpio del módulo (sin '+', wa.me-ready)
        assert get_settings(biz.id).whatsapp_phone == '573001555000'

    def test_token_is_single_use(self, db, biz):
        consume_setup_token(biz.slug, 'token-secreto-123', '4321')
        with pytest.raises(PosAuthError, match='ya fue usado'):
            consume_setup_token(biz.slug, 'token-secreto-123', '9999')

    def test_weak_pin_rejected_token_kept(self, db, biz):
        with pytest.raises(PosAuthError, match='4'):
            consume_setup_token(biz.slug, 'token-secreto-123', '12')
        # El token sigue vivo: el dueño puede reintentar
        assert biz.pos_setup_token == 'token-secreto-123'
        assert has_pos_pin(biz.id) is False

    def test_login_works_after_setup(self, db, biz):
        consume_setup_token(biz.slug, 'token-secreto-123', '4321')
        business = login_pos(biz.slug, '4321', ip='1.2.3.4')
        assert business.id == biz.id

    def test_whatsapp_optional(self, db, biz):
        consume_setup_token(biz.slug, 'token-secreto-123', '4321')
        from verduras.services.sales import get_settings
        assert get_settings(biz.id).whatsapp_phone is None


# ═════════════════ Rutas del POS ═════════════════


class TestSetupRoutes:
    def test_get_form_with_valid_token(self, client, db, biz):
        res = client.get(f'/pos/setup/{biz.slug}/token-secreto-123')
        assert res.status_code == 200
        assert b'Configura el POS' in res.data
        assert b'csrf_token' in res.data  # el POST estará protegido

    def test_get_form_with_dead_token_redirects(self, client, db, biz):
        res = client.get(f'/pos/setup/{biz.slug}/token-falso',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_post_consumes_and_enables_login(self, client, db, biz):
        res = client.post(f'/pos/setup/{biz.slug}/token-secreto-123',
                          data={'pin': '4321', 'pin2': '4321',
                                'whatsapp_phone': '+573001999888'},
                          follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

        # El PIN quedó funcionando (login real por sesión)
        res = client.post('/pos/login',
                          data={'slug': biz.slug, 'pin': '4321'},
                          follow_redirects=False)
        assert res.status_code == 302
        assert f'/pos/{biz.slug}'.encode() in res.data

    def test_post_pin_mismatch_keeps_token(self, client, db, biz):
        res = client.post(f'/pos/setup/{biz.slug}/token-secreto-123',
                          data={'pin': '4321', 'pin2': '9999'},
                          follow_redirects=False)
        assert res.status_code == 302
        assert f'/pos/setup/{biz.slug}/'.encode() in res.data or \
            'setup' in res.headers['Location']
        assert biz.pos_setup_token == 'token-secreto-123'
        assert has_pos_pin(biz.id) is False

    def test_post_with_dead_token_rejected(self, client, db, biz):
        res = client.post(f'/pos/setup/{biz.slug}/token-falso',
                          data={'pin': '4321', 'pin2': '4321'},
                          follow_redirects=True)
        # POST redirige al form con flash; el form (token muerto) al login
        assert res.request.path == '/pos/login'
        assert has_pos_pin(biz.id) is False

"""
Selector de mundos post-registro (`/register/vertical`).

Cubre:
- Acceso explícito: sin sesión → /register; con tenant → dashboard;
  sin tenant → 200 con tarjetas desde VERTICALS.
- Tarjetas: restaurante y verdurería con link; delivery/farmacia como
  "Próximamente" sin link.
- Fork: pick restaurante → setup-account; pick verdurería → register_verduras.
- `selected_vertical` se consume con pop (no permanece en sesión).
- Compatibilidad: /register manda al selector; /register/verduras directo
  sigue funcionando sin selected_vertical.
"""
import itertools

from werkzeug.security import generate_password_hash

from app.models import Business, User
from app.utils.verticals import (
    DEFAULT_VERTICAL,
    VERTICALS,
    get_enabled_vertical,
    user_has_tenant,
)

_user_seq = itertools.count(100)


def _mk_bare_user(db, email):
    user = User(username=f'Mundo {next(_user_seq)}', email=email,
                password=generate_password_hash('Secreta1'))
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


def _session_vertical(client):
    with client.session_transaction() as sess:
        return sess.get('selected_vertical', '<ausente>')


# ═════════════════ Registro centralizado ═════════════════


class TestVerticalsRegistry:
    def test_mundos_activos_con_setup(self):
        slugs = [v['slug'] for v in VERTICALS if v['enabled']]
        assert slugs == ['restaurant', 'verduras']
        for v in VERTICALS:
            if v['enabled']:
                assert v['setup_route'], v['slug']

    def test_futuros_sin_link(self):
        assert get_enabled_vertical('delivery') is None
        assert get_enabled_vertical('farmacia') is None
        assert get_enabled_vertical('inexistente') is None
        assert get_enabled_vertical('restaurant')['setup_route'] == 'auth.setup_account'
        assert get_enabled_vertical('verduras')['setup_route'] == 'auth.register_verduras'

    def test_tenant_cubre_restaurante_y_business(self, db, sample_user):
        assert user_has_tenant(sample_user) is True  # sample_user tiene restaurante
        bare = _mk_bare_user(db, 'sintenant@test.com')
        assert user_has_tenant(bare) is False
        assert user_has_tenant(None) is True
        biz = Business(id=1000001, vertical='verduras', name='V',
                       slug='v-mundo-test', owner_user_id=bare.id)
        db.session.add(biz)
        db.session.commit()
        assert user_has_tenant(bare) is True

    def test_default_es_restaurante(self):
        assert DEFAULT_VERTICAL == 'restaurant'


# ═════════════════ Página del selector ═════════════════


class TestRegisterVerticalPage:
    def test_sin_sesion_redirige_a_register(self, client):
        resp = client.get('/register/vertical')
        assert resp.status_code == 302
        assert '/register' in resp.headers['Location']

    def test_con_restaurante_va_al_dashboard(self, client, sample_user):
        _login(client, sample_user)
        resp = client.get('/register/vertical')
        assert resp.status_code == 302
        assert '/dashboard' in resp.headers['Location'] or 'dashboard' in resp.headers['Location']

    def test_con_business_propio_va_al_dashboard(self, client, db):
        bare = _mk_bare_user(db, 'duenomundo@test.com')
        db.session.add(Business(id=1000002, vertical='verduras', name='V',
                                slug='v-mundo-dash', owner_user_id=bare.id))
        db.session.commit()
        _login(client, bare)
        resp = client.get('/register/vertical')
        assert resp.status_code == 302

    def test_sin_tenant_muestra_tarjetas(self, client, db):
        _login(client, _mk_bare_user(db, 'explorador@test.com'))
        resp = client.get('/register/vertical')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Restaurante' in html
        assert 'Verdurer' in html  # Verdurería (con o sin tilde en slug/título)
        assert 'Próximamente' in html
        assert '/register/vertical/elegir/restaurant' in html
        assert '/register/vertical/elegir/verduras' in html
        assert '/register/vertical/elegir/delivery' not in html
        assert '/register/vertical/elegir/farmacia' not in html


# ═════════════════ Fork por mundo ═════════════════


class TestRegisterVerticalPick:
    def test_pick_restaurante_lleva_a_setup(self, client, db):
        _login(client, _mk_bare_user(db, 'rest@test.com'))
        resp = client.get('/register/vertical/elegir/restaurant')
        assert resp.status_code == 302
        assert 'setup-account' in resp.headers['Location']
        assert _session_vertical(client) == 'restaurant'

    def test_pick_verduras_lleva_a_su_registro(self, client, db):
        _login(client, _mk_bare_user(db, 'verde@test.com'))
        resp = client.get('/register/vertical/elegir/verduras')
        assert resp.status_code == 302
        assert 'verduras' in resp.headers['Location']
        assert _session_vertical(client) == 'verduras'

    def test_pick_deshabilitado_vuelve_al_selector(self, client, db):
        _login(client, _mk_bare_user(db, 'futuro@test.com'))
        resp = client.get('/register/vertical/elegir/delivery',
                          follow_redirects=False)
        assert resp.status_code == 302
        assert 'vertical' in resp.headers['Location']
        assert _session_vertical(client) == '<ausente>'

    def test_pick_invalido_vuelve_al_selector(self, client, db):
        _login(client, _mk_bare_user(db, 'raro@test.com'))
        resp = client.get('/register/vertical/elegir/narnia')
        assert resp.status_code == 302
        assert 'vertical' in resp.headers['Location']

    def test_pick_con_tenant_va_al_dashboard(self, client, sample_user):
        _login(client, sample_user)
        resp = client.get('/register/vertical/elegir/verduras')
        assert resp.status_code == 302


# ═════════════════ Consumo con pop + compatibilidad ═════════════════


class TestVerticalSessionConsumption:
    def test_setup_consume_el_vertical(self, client, db):
        """Entrar a setup-account consume selected_vertical (pop)."""
        _login(client, _mk_bare_user(db, 'pop@test.com'))
        client.get('/register/vertical/elegir/restaurant')
        assert _session_vertical(client) == 'restaurant'
        resp = client.get('/setup-account')
        assert resp.status_code == 200
        assert _session_vertical(client) == '<ausente>'

    def test_setup_con_verduras_rancia_redirige_y_limpia(self, client, db):
        _login(client, _mk_bare_user(db, 'rancia@test.com'))
        client.get('/register/vertical/elegir/verduras')
        resp = client.get('/setup-account')
        assert resp.status_code == 302
        assert 'verduras' in resp.headers['Location']
        assert _session_vertical(client) == '<ausente>'

    def test_setup_directo_sigue_en_restaurante(self, client, db):
        """Sin pick previo (deep link viejo): default restaurante, 200."""
        _login(client, _mk_bare_user(db, 'directo@test.com'))
        resp = client.get('/setup-account')
        assert resp.status_code == 200

    def test_register_manda_al_selector(self, client, db):
        _login(client, _mk_bare_user(db, 'fork@test.com'))
        resp = client.get('/register')
        assert resp.status_code == 302
        assert 'vertical' in resp.headers['Location']

    def test_register_verduras_directo_sigue_vivo(self, client, db):
        """La puerta vieja por URL no exige selected_vertical."""
        _login(client, _mk_bare_user(db, 'directoverde@test.com'))
        resp = client.get('/register/verduras')
        assert resp.status_code == 200

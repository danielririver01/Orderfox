"""Tests del Hub de Mundos.

Multi-Mundos v2: el Hub (tus mundos + agregar según plan) vive en el
SELECTOR de mundos (`/register/vertical` en modo con-tenant) — una única
superficie para listar, entrar y activar mundos. `/dashboard/mundos` es
un redirect de compatibilidad hacia el selector. Los tests cubren:
- Redirect de compatibilidad (bookmarks, enlaces antiguos).
- Modo hub en el selector: tarjetas con chip de estado, Entrar al POS
  de verduras, cupo del plan, cupo lleno → upgrade.
- World Switcher (context processor): se alimenta de la misma lista
  compartida (build_user_worlds) y no se renderiza para empleados.
"""
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app.models import Business, Restaurant, User

_user_seq = iter(__import__('itertools').count(600))


def _mk_owner(db, email, plan='emprendedor'):
    user = User(username=f'Dueño {next(_user_seq)}', email=email,
                password=generate_password_hash('Secreta1'))
    user.plan_type = plan
    user.subscription_expires_at = (
        datetime.now(timezone.utc) + timedelta(days=30))
    db.session.add(user)
    db.session.commit()
    return user


def _mk_restaurant(db, user, name='Rest Hub', slug=None):
    seq = next(_user_seq)
    r = Restaurant(name=name, slug=slug or f'rest-hub-{seq}',
                   whatsapp_phone='+573001112233', is_active=True,
                   subscription_expires_at=(
                       datetime.now(timezone.utc) + timedelta(days=30)))
    db.session.add(r)
    db.session.flush()
    user.restaurant_id = r.id
    db.session.commit()
    return r


def _mk_verduras(db, user, name):
    seq = next(_user_seq)
    biz = Business.create_direct('verduras', name, f'verd-hub-{seq}')
    biz.owner_user_id = user.id
    db.session.commit()
    return biz


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


class TestHubCompatRedirect:
    def test_dashboard_mundos_redirects_to_selector(self, client, app, db):
        """/dashboard/mundos es red de compatibilidad → selector (modo hub)."""
        user = _mk_owner(db, 'hubc@test.com')
        _login(client, user)
        resp = client.get('/dashboard/mundos', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/register/vertical')

    def test_redirect_lands_on_hub(self, client, app, db):
        """Siguiendo el redirect se llega al hub con contenido real."""
        user = _mk_owner(db, 'hubd@test.com')
        _mk_restaurant(db, user, 'Restaurante El Hub')
        _login(client, user)
        resp = client.get('/dashboard/mundos', follow_redirects=True)
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'Tus mundos' in html
        assert 'Restaurante El Hub' in html


class TestHubInSelector:
    def test_owner_with_restaurant_and_verduras(self, client, app, db):
        user = _mk_owner(db, 'hub1@test.com')
        _mk_restaurant(db, user, 'Restaurante El Hub')
        biz = _mk_verduras(db, user, 'Verduras La 14')
        _login(client, user)

        resp = client.get('/register/vertical')
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'Restaurante El Hub' in html
        assert 'Verduras La 14' in html
        # Chip de estado y cupo del plan presentes.
        assert 'Activo' in html
        assert 'Cupo del plan' in html
        # Enlace al POS del módulo (cross-app, handoff SSO).
        assert f'/pos/{biz.slug}' in html
        # Enlace Entrar al dashboard de core para el restaurante.
        assert '/dashboard' in html

    def test_quota_full_shows_upgrade(self, client, app, db):
        """Emprendedor = 2 mundos: con restaurante + verduras el cupo está
        lleno → tarjeta de upgrade, sin tarjetas de activar."""
        user = _mk_owner(db, 'hub2@test.com', plan='emprendedor')
        _mk_restaurant(db, user)
        _mk_verduras(db, user, 'Verduras Dos')
        _login(client, user)

        resp = client.get('/register/vertical')
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'Cupo lleno' in html
        assert 'Aumentar capacidad' in html

    def test_quota_available_shows_activate(self, client, app, db):
        user = _mk_owner(db, 'hub3@test.com', plan='crecimiento')
        _mk_restaurant(db, user)
        _login(client, user)

        resp = client.get('/register/vertical')
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'Activar' in html

    def test_elite_unlimited_card(self, client, app, db):
        """Élite CON mundos: la línea de cupo dice "mundos ilimitados"."""
        user = _mk_owner(db, 'hub4@test.com', plan='elite')
        _mk_restaurant(db, user)
        _login(client, user)

        resp = client.get('/register/vertical')
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'ilimitados' in html


class TestWorldSwitcherContext:
    def test_user_worlds_built_for_owner(self, client, app, db):
        """El switcher se alimenta de la MISMA lista compartida que el hub."""
        user = _mk_owner(db, 'sw1@test.com')
        _mk_restaurant(db, user, 'Restaurante Switch')
        biz = _mk_verduras(db, user, 'Verduras Switch')
        _login(client, user)

        # Cualquier página con base.html renderiza el switcher.
        resp = client.get('/dashboard/subscription')
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'world-switcher' in html
        assert 'Restaurante Switch' in html
        assert 'Verduras Switch' in html
        assert f'/pos/{biz.slug}' in html

    def test_switcher_absent_for_anonymous(self, client):
        resp = client.get('/register')
        html = resp.get_data(as_text=True)
        assert 'world-switcher' not in html

    def test_employee_without_worlds_no_switcher(self, client, app, db):
        """Un User sin restaurante ni businesses: user_worlds vacío (sin
        switcher) y el selector cae en modo registro sin petar."""
        user = _mk_owner(db, 'sw3@test.com')
        user.restaurant_id = None
        db.session.commit()
        _login(client, user)
        resp = client.get('/register/vertical')
        html = resp.get_data(as_text=True)
        # Sin tenant → modo registro (elige tu primer negocio).
        assert resp.status_code == 200
        assert 'negocio tienes' in html

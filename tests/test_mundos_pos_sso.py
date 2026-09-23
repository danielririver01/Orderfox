"""
Handoff Mundos → POS lado core: el dueño emite el token SSO (Tier GUARDIAN).

Cubre (2 tests):
- Dueño del mundo → 302 a la app del módulo con el token en la URL y
  token vivo en DB.
- Usuario logueado que NO es dueño → 404 (no revelar slugs ajenos).
"""
import pytest
from werkzeug.security import generate_password_hash

from app.models import Business, User

pytestmark = pytest.mark.guardian

_seq = iter(__import__('itertools').count(900))


def _mk_user(db, email):
    u = User(username=f'SSO {next(_seq)}', email=email,
             password=generate_password_hash('Secreta1'))
    db.session.add(u)
    db.session.commit()
    return u


def _mk_verduras(db, user, slug):
    biz = Business.create_direct('verduras', 'Verduras SSO Core', slug)
    biz.owner_user_id = user.id
    db.session.commit()
    return biz


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


class TestMundosPosSso:
    def test_owner_mints_and_redirects_to_module(self, client, db):
        user = _mk_user(db, 'sso-owner@test.com')
        biz = _mk_verduras(db, user, 'sso-core-1')
        _login(client, user)

        res = client.get(f'/dashboard/mundos/pos/{biz.slug}',
                         follow_redirects=False)
        assert res.status_code == 302
        location = res.headers['Location']
        assert f'/pos/sso/{biz.slug}/' in location
        db.session.expire_all()
        assert biz.pos_sso_token is not None
        assert location.endswith(f'/pos/sso/{biz.slug}/{biz.pos_sso_token}')

    def test_non_owner_gets_404(self, client, db):
        owner = _mk_user(db, 'sso-owner2@test.com')
        biz = _mk_verduras(db, owner, 'sso-core-2')
        intruder = _mk_user(db, 'sso-intruso@test.com')
        _login(client, intruder)

        res = client.get(f'/dashboard/mundos/pos/{biz.slug}',
                         follow_redirects=False)
        assert res.status_code == 404

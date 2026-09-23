"""
Handoff Mundos → POS: el dueño entra al mostrador sin PIN (Tier GUARDIAN).

Cubre (5 tests, tope del modelo):
- Token válido se consume una vez: abre sesión y el enlace muere.
- Reúso del mismo enlace → login de mostrador.
- Expirado → login (y se limpia).
- Token ajeno / slug inexistente → login con mensaje genérico.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Business
from verduras.services.pos_auth import mint_pos_sso_token

pytestmark = pytest.mark.guardian


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'sso-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras SSO', slug=_slug())


class TestPosSso:
    def test_valid_token_opens_session_and_dies(self, client, db, biz):
        token = mint_pos_sso_token(biz.id)
        res = client.get(f'/pos/sso/{biz.slug}/{token}',
                         follow_redirects=False)
        assert res.status_code == 302
        assert f'/pos/{biz.slug}' in res.headers['Location']
        db.session.expire_all()
        assert biz.pos_sso_token is None  # un solo uso

        # La sesión quedó abierta: el POS carga sin PIN.
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200

    def test_reuse_rejected(self, client, db, biz):
        token = mint_pos_sso_token(biz.id)
        client.get(f'/pos/sso/{biz.slug}/{token}')
        res = client.get(f'/pos/sso/{biz.slug}/{token}',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_expired_rejected_and_cleaned(self, client, db, biz):
        token = mint_pos_sso_token(biz.id)
        biz.pos_sso_expires_at = (
            datetime.now(timezone.utc) - timedelta(minutes=1))
        db.session.commit()
        res = client.get(f'/pos/sso/{biz.slug}/{token}',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']
        db.session.expire_all()
        assert biz.pos_sso_token is None  # no deja basura válida a medias

    def test_foreign_token_rejected(self, client, db, biz):
        mint_pos_sso_token(biz.id)
        res = client.get(f'/pos/sso/{biz.slug}/{'x' * 43}',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_unknown_slug_rejected(self, client, db, biz):
        token = mint_pos_sso_token(biz.id)
        res = client.get(f'/pos/sso/no-existe/{token}',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

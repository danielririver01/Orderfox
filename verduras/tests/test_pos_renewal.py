"""
Tests de suscripción en el POS (lado módulo).

Cubren:
- POS con suscripción vigente → vende normal (comportamiento intacto).
- POS en gracia/vencido → pantalla pos_renewal (con URL de renovación a core),
  jamás un 500, jamás una venta.
- Business legacy (piloto, sin dueño ni fecha) → POS normal (sin bloqueo).
- ensure_business_active delega en core (el módulo no decide fechas).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from app.models import Business, User
from verduras.services.catalog import create_category, create_product
from verduras.services.context import (
    BusinessInactiveError,
    ensure_business_active,
    get_subscription_status,
)


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'pos-sub-{_slug.n}'


def _mk_pos_biz(db, *, owner=False, expires_in=30):
    slug = _slug()
    biz = Business.create_direct('verduras', f'Verduras {slug}', slug)
    if owner:
        user = User(username=f'Dueño {slug}', email=f'{slug}@test.com',
                    password=generate_password_hash('Secreta1'))
        db.session.add(user)
        db.session.commit()
        biz.owner_user_id = user.id
    if expires_in is not None:
        biz.subscription_expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in))
    db.session.commit()
    return biz


@pytest.fixture()
def biz(db):
    return _mk_pos_biz(db, owner=True)


@pytest.fixture()
def products(db, biz):
    cat = create_category(biz.id, 'Hortalizas')
    tomate = create_product(biz.id, cat.id, 'Tomate', 'kg', '3200.00')
    return SimpleNamespace(tomate=tomate)


def _login_pos(client, biz):
    """Login directo de sesión POS (el PIN ya lo cubre test_pos.py)."""
    from verduras.services import pos_auth
    with client.session_transaction() as sess:
        sess[pos_auth.SESSION_KEY] = biz.id


# ═════════════════ POS: bloqueo por suscripción ═════════════════


class TestPosSubscriptionGate:
    def test_active_subscription_renders_pos(self, client, db, biz):
        _login_pos(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert 'gracia' not in res.data.decode().lower()

    def test_grace_period_shows_renewal_screen(self, client, app, db):
        biz = _mk_pos_biz(db, expires_in=-2)
        _login_pos(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert 'gracia' in res.data.decode().lower()
        assert '/renew' in res.data.decode()  # enlace de renovación a core

    def test_expired_shows_renewal_screen(self, client, app, db):
        biz = _mk_pos_biz(db, expires_in=-45)
        _login_pos(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        page = res.data.decode().lower()
        assert 'renovar' in page and 'expirada' in page

    def test_legacy_without_owner_never_blocked(self, client, db):
        """Piloto: sin dueño ni fecha → el POS funciona igual que siempre."""
        biz = _mk_pos_biz(db, owner=False, expires_in=None)
        _login_pos(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert 'gracia' not in res.data.decode().lower()

    def test_sale_blocked_when_expired(self, client, db, products):
        biz = _mk_pos_biz(db, expires_in=-3)
        _login_pos(client, biz)
        res = client.post(
            f'/pos/{biz.slug}/sell',
            json={'items': [{'product_id': products.tomate.id,
                             'quantity': 1, 'weight_kg': '0.5'}]},
            content_type='application/json')
        # La venta por sesión NO debe procesarse con la suscripción vencida
        assert res.status_code in (401, 403, 409)


# ═════════════════ Servicio: delegación a core ═════════════════


class TestContextSubscription:
    def test_ensure_active_passes(self, db, biz):
        ensure_business_active(biz)  # no levanta

    def test_ensure_active_raises_with_status(self, db):
        biz = _mk_pos_biz(db, expires_in=-2)
        with pytest.raises(BusinessInactiveError) as exc:
            ensure_business_active(biz)
        assert exc.value.status['status'] == 'grace_period'

    def test_get_status_delegates_to_core(self, db, biz):
        status = get_subscription_status(biz)
        assert status['status'] == 'active'
        assert status['can_crud'] is True

"""Tier DESECHABLE (extraído de test_skeleton.py).

Smoke del andamio Semana 0: endpoints base + 404 JSON. Ya cumplió su
propósito. No corre en CI (verify_*.py). Correr explícito:
    pytest verduras/tests/verify_verduras_skeleton.py
Si pasan 30 días sin correrlo, borrar sin discusión.
"""
from app.models import Business, Restaurant


def _s_slug():
    """Slug único por test (los slugs son unique)."""
    _s_slug.n = getattr(_s_slug, 'n', 0) + 1
    return f'verduras-{_s_slug.n}'


def _s_mk_restaurant(db):
    """Crea un Restaurant de core; el puente genera su Business espejo."""
    r = Restaurant(
        name=f'Rest {_s_slug()}',
        slug=_s_slug(),
        whatsapp_phone='+573001112233',
    )
    db.session.add(r)
    db.session.flush()
    return r


def _s_mk_verduras_business(db):
    """Business directo del vertical (banda >= 1_000_000)."""
    return Business.create_direct(vertical='verduras', name='Verduras La Central',
                                  slug=_s_slug())


class TestBaseEndpoints:
    def test_index(self, client):
        res = client.get('/')
        assert res.status_code == 200
        body = res.get_json()
        assert body['success'] is True
        assert body['module'] == 'verduras'

    def test_health_ok(self, client):
        res = client.get('/health')
        assert res.status_code == 200
        body = res.get_json()
        assert body['success'] is True
        assert body['database'] is True

    def test_health_core_bridge_counts(self, client, db):
        _s_mk_restaurant(db)
        _s_mk_verduras_business(db)
        res = client.get('/health/core-bridge')
        assert res.status_code == 200
        bridge = res.get_json()['bridge']
        assert bridge['restaurant_mirrors'] >= 1
        assert bridge['verduras_businesses'] >= 1

    def test_404_json(self, client):
        res = client.get('/no-existe')
        assert res.status_code == 404
        assert res.get_json()['error_code'] == 'not_found'

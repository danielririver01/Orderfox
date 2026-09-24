"""Aislamiento de tenant (IDOR): un negocio jamás toca datos de otro.

Tier GUARDIAN: si falla, hay fuga de datos entre negocios (dinero/datos).
"""
from datetime import datetime, timezone, timedelta

from flask_jwt_extended import create_access_token

from app.models import Restaurant, User, Category, Product


def _second_tenant(db):
    r = Restaurant(
        name='Otro Negocio',
        slug='otro-negocio',
        whatsapp_phone='+573007777777',
        plan_type='emprendedor',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.flush()
    c = Category(restaurant_id=r.id, name='Otros', sort_order=1, is_active=True)
    db.session.add(c)
    db.session.flush()
    p = Product(restaurant_id=r.id, category_id=c.id, name='Secreto',
                price=9999, is_active=True)
    db.session.add(p)
    db.session.commit()
    return r, p


def _jwt_for(app, user):
    with app.app_context():
        return create_access_token(identity=str(user.id))


class TestTenantIsolation:
    def test_cross_tenant_product_detail_404(
            self, app, client, db, sample_user, sample_product):
        _r2, p2 = _second_tenant(db)
        token = _jwt_for(app, sample_user)
        resp = client.get(
            f'/api/products/{p2.id}',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 404

    def test_cross_tenant_product_list_isolated(
            self, app, client, db, sample_user, sample_product):
        _r2, _p2 = _second_tenant(db)
        token = _jwt_for(app, sample_user)
        resp = client.get(
            '/api/products',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 200
        names = [p['name'] for p in resp.get_json()['data']['products']]
        assert names == ['Coca Cola']

    def test_s2s_ignores_query_identity(self, app, client, db, sample_user):
        """La identidad S2S viaja SOLO en body JSON: ?clerk_id= se ignora."""
        old = app.config.get('SERVICE_API_KEY')
        app.config['SERVICE_API_KEY'] = 'test-s2s-key'
        try:
            headers = {'x-api-key': 'test-s2s-key'}
            # Solo query, body vacío → 401 (identidad en query está muerta).
            r1 = client.post('/api/tokens/consume?clerk_id=clerk_test_123',
                             headers=headers)
            assert r1.status_code == 401
            # Misma identidad en body → resuelta (200 o 403 por wallet,
            # pero NUNCA 401).
            r2 = client.post('/api/tokens/consume',
                             json={'clerk_id': 'clerk_test_123'},
                             headers=headers)
            assert r2.status_code in (200, 403)
        finally:
            app.config['SERVICE_API_KEY'] = old

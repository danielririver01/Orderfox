"""
Idempotencia de creación de pedidos (v1.5).

Un reintento del cliente (doble tap, respuesta perdida en red, re-POST del
navegador) con la misma idempotency_key NO debe crear un pedido duplicado:
debe devolver el pedido original. Cobertura:

1. OrderService.create_order_idempotent: replay, key distinta, sin key.
2. PublicMenuService.create_order_from_cart: replay con items originales.
3. Ruta pública /menu/api/order: POST repetido → un solo pedido.
4. POS empleado /<slug>/pedidos/nuevo: doble submit → un solo pedido.
"""
import json
import re
import uuid

import pytest

from app.models import db, Order
from app.services.order_service import OrderService
from app.services.public_menu_service import PublicMenuService


def _csrf_headers(client, url):
    """Extrae el token CSRF de una página de la sesión activa (patrón del repo:
    el before_request manual de app/__init__.py protege /empleado/* aunque
    WTF_CSRF_ENABLED esté en False en tests)."""
    page = client.get(url)
    m = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
    assert m, f'no se encontró el token CSRF en {url}'
    return {'X-CSRFToken': m.group(1)}


# ── Helpers ──────────────────────────────────────────────────────────────

def _order_data(**overrides):
    data = {
        'customer_name': 'Cliente Test',
        'customer_phone': '+573001234567',
        'notes': '',
        'pending_expiry_hours': 24,
    }
    data.update(overrides)
    return data


# ── 1. Service layer ─────────────────────────────────────────────────────

class TestCreateOrderIdempotent:

    def test_same_key_returns_original_order(self, db, sample_restaurant):
        """Reintento con la misma clave → mismo pedido, no duplicado."""
        key = str(uuid.uuid4())

        order1, created1 = OrderService.create_order_idempotent(
            sample_restaurant.id, _order_data(idempotency_key=key))
        db.session.commit()

        order2, created2 = OrderService.create_order_idempotent(
            sample_restaurant.id, _order_data(idempotency_key=key))

        assert created1 is True
        assert created2 is False
        assert order1.id == order2.id
        assert Order.query.filter_by(
            restaurant_id=sample_restaurant.id).count() == 1

    def test_different_key_creates_new_order(self, db, sample_restaurant):
        """Claves distintas = pedidos distintos (comportamiento normal)."""
        o1, c1 = OrderService.create_order_idempotent(
            sample_restaurant.id,
            _order_data(idempotency_key=str(uuid.uuid4())))
        o2, c2 = OrderService.create_order_idempotent(
            sample_restaurant.id,
            _order_data(idempotency_key=str(uuid.uuid4())))

        assert c1 is True and c2 is True
        assert o1.id != o2.id

    def test_no_key_backward_compatible(self, db, sample_restaurant):
        """Sin clave (callers viejos) funciona igual que siempre."""
        o1, c1 = OrderService.create_order_idempotent(
            sample_restaurant.id, _order_data())
        o2, c2 = OrderService.create_order_idempotent(
            sample_restaurant.id, _order_data())

        assert c1 is True and c2 is True
        assert o1.id != o2.id
        assert o1.idempotency_key is None

    def test_key_scoped_to_restaurant(self, db, sample_restaurant, sample_restaurant_2=None):
        """La misma clave en OTRO restaurante SÍ crea su pedido (scope)."""
        from app.models import Restaurant
        other = Restaurant(
            name='Otro', slug='otro-rest-idem',
            whatsapp_phone='+573009999999', plan_type='emprendedor',
            is_active=True, is_open=True)
        db.session.add(other)
        db.session.commit()

        key = str(uuid.uuid4())
        o1, _ = OrderService.create_order_idempotent(
            sample_restaurant.id, _order_data(idempotency_key=key))
        o2, c2 = OrderService.create_order_idempotent(
            other.id, _order_data(idempotency_key=key))

        assert c2 is True  # la clave es única POR restaurante
        assert o1.id != o2.id

    def test_create_order_signature_unchanged(self, db, sample_restaurant):
        """create_order (API vieja) sigue devolviendo solo Order."""
        order = OrderService.create_order(sample_restaurant.id, _order_data())
        assert isinstance(order, Order)
        assert order.id is not None


# ── 2. PublicMenuService ─────────────────────────────────────────────────

class TestCreateOrderFromCartIdempotent:

    def _cart_call(self, restaurant, product, key):
        return PublicMenuService.create_order_from_cart(
            restaurant=restaurant,
            cart={product.id: {'quantity': 2, 'extras': []}},
            customer_name='Cliente Web',
            customer_phone='+573001234567',
            notes='Nota',
            table_id=None,
            ip_address='127.0.0.1',
            order_number='ORD-IDEM-1',
            idempotency_key=key,
        )

    def test_replay_returns_original_with_items(
            self, db, sample_restaurant, sample_product):
        key = str(uuid.uuid4())

        order1, items1, total1, created1 = self._cart_call(
            sample_restaurant, sample_product, key)
        db.session.commit()

        order2, items2, total2, created2 = self._cart_call(
            sample_restaurant, sample_product, key)

        assert created1 is True and created2 is False
        assert order1.id == order2.id
        assert order2.total == total1
        assert len(items2) == 1  # items del original, no duplicados
        assert Order.query.filter_by(
            restaurant_id=sample_restaurant.id).count() == 1


# ── 3. Ruta pública /menu/api/order ──────────────────────────────────────

@pytest.fixture
def public_open_restaurant(db, sample_restaurant):
    sample_restaurant.is_open = True
    db.session.commit()
    return sample_restaurant


class TestPublicOrderRouteIdempotent:

    def _post(self, client, restaurant, product, key, cart_payload=None):
        cart = cart_payload or {
            str(product.id): {'quantity': 1, 'extras': []}
        }
        return client.post('/menu/api/order', json={
            'restaurant_id': restaurant.id,
            'cart': cart,
            'customer_name': 'Cliente Web',
            'customer_phone': '+573001234567',
            'idempotency_key': key,
        })

    def test_repeated_post_with_same_key_creates_one_order(
            self, client, db, public_open_restaurant, sample_product):
        import time as _time
        with client.session_transaction() as sess:
            sess['checkout_start_time'] = _time.time() - 5

        key = str(uuid.uuid4())

        r1 = self._post(client, public_open_restaurant, sample_product, key)
        assert r1.status_code == 200, r1.get_data(as_text=True)
        r2 = self._post(client, public_open_restaurant, sample_product, key)

        assert r2.status_code == 200
        body = r2.get_json()
        assert body['success'] is True
        # El segundo POST devuelve EL MISMO pedido (mismo id/número)
        assert body['order_id'] == r1.get_json()['order_id']
        assert body['order_number'] == r1.get_json()['order_number']
        assert Order.query.filter_by(
            restaurant_id=public_open_restaurant.id).count() == 1


# ── 4. POS del empleado ──────────────────────────────────────────────────

# Fixtures locales: las de trazabilidad viven en su propio módulo, no en
# conftest. Patrón idéntico a test_order_traceability.py.

@pytest.fixture
def pos_restaurant(db):
    from app.models import Restaurant
    from datetime import datetime, timezone, timedelta
    r = Restaurant(
        name='POS Restaurant',
        slug='pos-restaurant',
        whatsapp_phone='+573007777777',
        plan_type='elite',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def pos_waiter(db, pos_restaurant):
    from app.services.employee_service import EmployeeService
    return EmployeeService.create_employee(pos_restaurant, 'Mesero POS', 'waiter', '9174')


@pytest.fixture
def pos_product(db, pos_restaurant):
    from app.models import Category, Product
    cat = Category(restaurant_id=pos_restaurant.id, name='Carta', sort_order=1, is_active=True)
    db.session.add(cat)
    db.session.flush()
    p = Product(restaurant_id=pos_restaurant.id, category_id=cat.id,
                name='Pizza POS', price=20000, is_active=True)
    db.session.add(p)
    db.session.commit()
    return p


class TestPosOrderRouteIdempotent:

    def test_double_submit_same_key_creates_one_order(
            self, client, db, pos_restaurant, pos_waiter, pos_product):
        with client.session_transaction() as sess:
            sess['employee_id'] = pos_waiter.id
            sess['employee_login'] = True
        headers = _csrf_headers(client, f'/empleado/{pos_restaurant.slug}/pedidos')

        key = str(uuid.uuid4())

        r1 = client.post(
            f'/empleado/{pos_restaurant.slug}/pedidos/nuevo',
            data={
                'items': json.dumps(
                    [{'product_id': pos_product.id, 'quantity': 2}]),
                'idempotency_key': key,
            }, headers=headers)
        assert r1.status_code == 302

        r2 = client.post(
            f'/empleado/{pos_restaurant.slug}/pedidos/nuevo',
            data={
                'items': json.dumps(
                    [{'product_id': pos_product.id, 'quantity': 2}]),
                'idempotency_key': key,
            }, headers=headers)
        assert r2.status_code == 302

        orders = Order.query.filter_by(
            restaurant_id=pos_restaurant.id).all()
        assert len(orders) == 1  # un solo pedido, no duplicado

    def test_no_key_still_creates_order(
            self, client, db, pos_restaurant, pos_waiter, pos_product):
        """Compatibilidad: POST sin clave (flujo viejo) crea el pedido."""
        with client.session_transaction() as sess:
            sess['employee_id'] = pos_waiter.id
            sess['employee_login'] = True
        headers = _csrf_headers(client, f'/empleado/{pos_restaurant.slug}/pedidos')

        r = client.post(
            f'/empleado/{pos_restaurant.slug}/pedidos/nuevo',
            data={'items': json.dumps(
                [{'product_id': pos_product.id, 'quantity': 1}])},
            headers=headers)
        assert r.status_code == 302
        assert Order.query.filter_by(
            restaurant_id=pos_restaurant.id).count() == 1

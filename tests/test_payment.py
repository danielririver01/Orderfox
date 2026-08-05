from datetime import datetime, timezone, timedelta

import pytest

from app.models import Order
from app.services.order_service import OrderService, PaymentValidationError


@pytest.fixture
def payment_order(db, sample_restaurant):
    o = Order(
        restaurant_id=sample_restaurant.id,
        order_number='ORD-PAY-001',
        customer_name='Cliente Pago',
        customer_phone='+573001234567',
        status='pending',
        total=25000,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(o)
    db.session.commit()
    return o


@pytest.fixture
def another_restaurant(db):
    from app.models import Restaurant
    r = Restaurant(
        name='Otro Restaurant',
        slug='otro-restaurant',
        whatsapp_phone='+573009999999',
        plan_type='emprendedor',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


class TestRecordPaymentService:
    """Tests de la lógica de negocio de record_payment (server-side)."""

    def test_cash_exact_amount(self, payment_order, db):
        order, change = OrderService.record_payment(
            payment_order, 'cash', amount_received=25000)
        assert order.payment_method == 'cash'
        assert order.amount_received == 25000
        assert order.change_due == 0
        assert change == 0
        assert order.paid_at is not None

    def test_cash_with_change(self, payment_order, db):
        order, change = OrderService.record_payment(
            payment_order, 'cash', amount_received=50000)
        assert change == 25000
        assert order.change_due == 25000
        assert order.amount_received == 50000

    def test_cash_insufficient_raises(self, payment_order, db):
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'cash', amount_received=10000)
        assert 'Falta dinero' in str(exc.value)
        assert exc.value.status_code == 400
        assert payment_order.payment_method is None

    def test_cash_zero_amount_raises(self, payment_order, db):
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'cash', amount_received=0)
        assert 'El monto recibido debe ser mayor a 0' in str(exc.value)

    def test_cash_negative_amount_raises(self, payment_order, db):
        with pytest.raises(PaymentValidationError):
            OrderService.record_payment(payment_order, 'cash', amount_received=-5000)

    def test_cash_non_numeric_raises(self, payment_order, db):
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'cash', amount_received='abc')
        assert 'Debes indicar cuánto recibiste del cliente' in str(exc.value)

    def test_cash_none_amount_raises(self, payment_order, db):
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'cash', amount_received=None)
        assert 'Debes indicar cuánto recibiste del cliente' in str(exc.value)

    def test_cash_string_number_accepted(self, payment_order, db):
        order, change = OrderService.record_payment(
            payment_order, 'cash', amount_received='25000')
        assert order.amount_received == 25000

    def test_nequi_forces_amounts_to_none(self, payment_order, db):
        order, change = OrderService.record_payment(
            payment_order, 'nequi', amount_received=999999, change_due=888)
        assert order.payment_method == 'nequi'
        assert order.amount_received is None
        assert order.change_due is None
        assert change is None

    def test_bancolombia_forces_amounts_to_none(self, payment_order, db):
        order, change = OrderService.record_payment(payment_order, 'bancolombia')
        assert order.payment_method == 'bancolombia'
        assert order.amount_received is None
        assert order.change_due is None
        assert change is None

    def test_card_forces_amounts_to_none(self, payment_order, db):
        order, change = OrderService.record_payment(payment_order, 'card')
        assert order.payment_method == 'card'
        assert order.amount_received is None
        assert order.change_due is None
        assert change is None

    def test_invalid_method_raises(self, payment_order, db):
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'bitcoin')
        assert 'Método de pago inválido' in str(exc.value)
        assert exc.value.status_code == 400

    def test_double_payment_rejected(self, payment_order, db):
        OrderService.record_payment(payment_order, 'cash', amount_received=25000)
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'card')
        assert 'ya tiene un pago registrado' in str(exc.value)
        assert exc.value.status_code == 409
        # El primer pago no se altera
        assert payment_order.payment_method == 'cash'
        assert payment_order.amount_received == 25000

    def test_cancelled_order_rejected(self, payment_order, db):
        payment_order.status = 'cancelled'
        db.session.commit()
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(payment_order, 'cash', amount_received=25000)
        assert 'cancelado' in str(exc.value)
        assert payment_order.payment_method is None

    def test_paid_at_set_in_utc(self, payment_order, db):
        before = datetime.now(timezone.utc)
        OrderService.record_payment(payment_order, 'card')
        after = datetime.now(timezone.utc)
        assert payment_order.paid_at is not None
        assert before <= payment_order.paid_at <= after

    def test_payment_committed_to_db(self, payment_order, db):
        OrderService.record_payment(payment_order, 'cash', amount_received=30000)
        reloaded = db.session.get(Order, payment_order.id)
        assert reloaded.payment_method == 'cash'
        assert reloaded.amount_received == 30000
        assert reloaded.change_due == 5000
        assert reloaded.paid_at is not None


class TestRegisterPaymentWebRoute:
    """Tests de la ruta web POST /orders/<id>/payment (JSON)."""

    import re as _re

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _csrf_headers(self, client):
        """La ruta web exige CSRF (protect() manual). Obtenemos el token del
        meta tag renderizado por base.html, como hace el frontend real."""
        page = client.get('/orders/')
        m = self._re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        token = m.group(1) if m else ''
        return {'X-CSRFToken': token}

    def _post_payment(self, client, order_id, payload):
        headers = self._csrf_headers(client)
        return client.post(f'/orders/{order_id}/payment', json=payload, headers=headers)

    def test_register_cash_payment(self, client, db, payment_order, sample_user):
        self._login(client, sample_user)
        resp = self._post_payment(client, payment_order.id, {
            'payment_method': 'cash',
            'amount_received': 30000,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['payment_method'] == 'cash'
        assert data['data']['amount_received'] == 30000
        assert data['data']['change_due'] == 5000
        assert data['data']['paid_at'] is not None

    def test_register_card_payment(self, client, db, payment_order, sample_user):
        self._login(client, sample_user)
        resp = self._post_payment(client, payment_order.id, {
            'payment_method': 'card',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['payment_method'] == 'card'
        assert data['data']['amount_received'] is None
        assert data['data']['change_due'] is None

    def test_insufficient_cash_returns_400(self, client, db, payment_order, sample_user):
        self._login(client, sample_user)
        resp = self._post_payment(client, payment_order.id, {
            'payment_method': 'cash',
            'amount_received': 5000,
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Falta dinero' in data['error']

    def test_missing_method_returns_400(self, client, db, payment_order, sample_user):
        self._login(client, sample_user)
        resp = self._post_payment(client, payment_order.id, {})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_invalid_method_returns_400(self, client, db, payment_order, sample_user):
        self._login(client, sample_user)
        resp = self._post_payment(client, payment_order.id, {
            'payment_method': 'paypal',
        })
        assert resp.status_code == 400
        assert 'Método de pago inválido' in resp.get_json()['error']

    def test_double_payment_returns_409(self, client, db, payment_order, sample_user):
        self._login(client, sample_user)
        first = self._post_payment(client, payment_order.id, {
            'payment_method': 'cash',
            'amount_received': 25000,
        })
        assert first.status_code == 200
        second = self._post_payment(client, payment_order.id, {
            'payment_method': 'card',
        })
        assert second.status_code == 409
        assert 'ya tiene un pago registrado' in second.get_json()['error']

    def test_order_from_other_restaurant_returns_404(self, client, db, sample_user, another_restaurant):
        """IDOR: un pedido de otro restaurante no debe ser registrable (scoping)."""
        from app.models import Order
        foreign_order = Order(
            restaurant_id=another_restaurant.id,
            order_number='ORD-OTRO-001',
            customer_name='Cliente Ajeno',
            status='pending',
            total=10000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add(foreign_order)
        db.session.commit()
        self._login(client, sample_user)
        resp = self._post_payment(client, foreign_order.id, {
            'payment_method': 'cash',
            'amount_received': 10000,
        })
        assert resp.status_code == 404
        assert foreign_order.payment_method is None

    def test_unauthenticated_returns_401(self, client, db, payment_order):
        """Sin sesión activa la ruta exige login (401 JSON). El CSRF manual del
        proyecto corre en before_request antes que el decorador require_auth,
        así que sin token CSRF la respuesta puede ser 400 (CSRF) o 401 (auth).
        Ambos son negativas de seguridad; lo importante es que no se registra."""
        resp = client.post(f'/orders/{payment_order.id}/payment',
                           json={'payment_method': 'card'})
        assert resp.status_code in (400, 401)
        reloaded = db.session.get(Order, payment_order.id)
        assert reloaded.payment_method is None


class TestRegisterPaymentApiRoute:
    """Tests de la ruta API POST /api/orders/<id>/payment (JWT)."""

    def _jwt_headers(self, client, user):
        from flask_jwt_extended import create_access_token
        with client.application.app_context():
            token = create_access_token(identity=str(user.id))
        return {'Authorization': f'Bearer {token}'}

    def test_register_cash_payment_api(self, client, db, payment_order, sample_user):
        resp = client.post(f'/api/orders/{payment_order.id}/payment',
                           json={'payment_method': 'cash', 'amount_received': 40000},
                           headers=self._jwt_headers(client, sample_user))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['change_due'] == 15000

    def test_api_insufficient_cash_400(self, client, db, payment_order, sample_user):
        resp = client.post(f'/api/orders/{payment_order.id}/payment',
                           json={'payment_method': 'cash', 'amount_received': 100},
                           headers=self._jwt_headers(client, sample_user))
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_api_double_payment_409(self, client, db, payment_order, sample_user):
        h = self._jwt_headers(client, sample_user)
        first = client.post(f'/api/orders/{payment_order.id}/payment',
                            json={'payment_method': 'card'}, headers=h)
        assert first.status_code == 200
        second = client.post(f'/api/orders/{payment_order.id}/payment',
                             json={'payment_method': 'cash', 'amount_received': 25000}, headers=h)
        assert second.status_code == 409

    def test_api_idor_returns_404(self, client, db, sample_user, another_restaurant):
        from app.models import Order
        foreign_order = Order(
            restaurant_id=another_restaurant.id,
            order_number='ORD-OTRO-API',
            customer_name='Cliente Ajeno',
            status='pending',
            total=10000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add(foreign_order)
        db.session.commit()
        resp = client.post(f'/api/orders/{foreign_order.id}/payment',
                           json={'payment_method': 'cash', 'amount_received': 10000},
                           headers=self._jwt_headers(client, sample_user))
        assert resp.status_code == 404

    def test_api_unauthenticated_401(self, client, db, payment_order):
        resp = client.post(f'/api/orders/{payment_order.id}/payment',
                           json={'payment_method': 'card'})
        assert resp.status_code == 401


@pytest.fixture
def order_with_items(db, sample_restaurant, sample_product):
    from app.models import Order, OrderItem
    o = Order(
        restaurant_id=sample_restaurant.id,
        order_number='ORD-EDIT-001',
        customer_name='Cliente Edit',
        status='pending',
        total=15000,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(o)
    db.session.flush()
    db.session.add(OrderItem(
        order_id=o.id,
        restaurant_id=sample_restaurant.id,
        product_name=sample_product.name,
        product_price=sample_product.price,
        quantity=3,
        subtotal=15000,
    ))
    db.session.commit()
    return o


class TestUpdateOrderItemsService:
    """Tests de la edición de items de una venta (server-side)."""

    def _items(self, product, qty):
        return [{'product_id': product.id, 'quantity': qty}]

    def test_change_quantity_updates_total(self, db, order_with_items, sample_product):
        total, _ = OrderService.update_order_items(
            order_with_items, self._items(sample_product, 2), sample_product.restaurant_id)
        assert total == 10000
        assert order_with_items.total == 10000
        assert len(order_with_items.items) == 1
        assert order_with_items.items[0].quantity == 2
        assert order_with_items.items[0].subtotal == 10000

    def test_remove_product_drops_item(self, db, order_with_items, sample_product):
        total, _ = OrderService.update_order_items(
            order_with_items, [], sample_product.restaurant_id)
        assert total == 0
        assert order_with_items.total == 0
        assert len(order_with_items.items) == 0

    def test_zero_quantity_drops_item(self, db, order_with_items, sample_product):
        total, _ = OrderService.update_order_items(
            order_with_items, self._items(sample_product, 0), sample_product.restaurant_id)
        assert total == 0
        assert len(order_with_items.items) == 0

    def test_negative_quantity_raises(self, db, order_with_items, sample_product):
        with pytest.raises(ValueError):
            OrderService.update_order_items(
                order_with_items, self._items(sample_product, -1), sample_product.restaurant_id)
        assert order_with_items.total == 15000

    def test_cancelled_order_rejected(self, db, order_with_items, sample_product):
        order_with_items.status = 'cancelled'
        db.session.commit()
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.update_order_items(
                order_with_items, self._items(sample_product, 1), sample_product.restaurant_id)
        assert 'cancelado' in str(exc.value)

    def test_cash_payment_recalculates_change(self, db, order_with_items, sample_product):
        """Bajar la venta con pago en efectivo recalcula el cambio."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        assert order_with_items.change_due == 5000

        OrderService.update_order_items(
            order_with_items, self._items(sample_product, 1), sample_product.restaurant_id)
        assert order_with_items.total == 5000
        assert order_with_items.amount_received == 20000
        assert order_with_items.change_due == 15000

    def test_cash_payment_new_total_exceeds_received(self, db, order_with_items, sample_product):
        """Subir la venta por encima de lo recibido bloquea la edición."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=15000)
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.update_order_items(
                order_with_items, self._items(sample_product, 5), sample_product.restaurant_id)
        assert 'supera el monto recibido' in str(exc.value)
        assert order_with_items.total == 15000

    def test_non_cash_payment_keeps_method(self, db, order_with_items, sample_product):
        OrderService.record_payment(order_with_items, 'card')
        OrderService.update_order_items(
            order_with_items, self._items(sample_product, 1), sample_product.restaurant_id)
        assert order_with_items.payment_method == 'card'
        assert order_with_items.total == 5000

    def test_preserves_modifiers_snapshot(self, db, order_with_items, sample_product):
        import json as _json
        order_with_items.items[0].modifiers_snapshot = _json.dumps(
            [{'name': 'Extra Queso', 'price': 2000}])
        db.session.commit()

        OrderService.update_order_items(
            order_with_items, self._items(sample_product, 2), sample_product.restaurant_id)
        snapshot = _json.loads(order_with_items.items[0].modifiers_snapshot)
        assert snapshot[0]['name'] == 'Extra Queso'


class TestEditOrderRoute:
    """Tests de la ruta web de edición de venta."""

    import re as _re

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _csrf_headers(self, client):
        page = client.get('/orders/')
        match = self._re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        assert match, 'no se encontró el token CSRF en /orders/'
        return {'X-CSRFToken': match.group(1)}

    def test_get_edit_page_renders(self, client, db, order_with_items, sample_user):
        self._login(client, sample_user)
        resp = client.get(f'/orders/{order_with_items.id}/edit')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Editar Venta' in body
        assert 'Guardar Cambios' in body

    def test_post_updates_quantity(self, client, db, order_with_items, sample_user, sample_product):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'Cliente Edit',
            'items': '[{"product_id": ' + str(sample_product.id) + ', "quantity": 2}]',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 10000
        assert reloaded.items[0].quantity == 2

    def test_post_empty_items_flash_error(self, client, db, order_with_items, sample_user, sample_product):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'Cliente Edit',
            'items': '[]',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 0

    def test_post_cancelled_order_redirects(self, client, db, order_with_items, sample_user, sample_product):
        order_with_items.status = 'cancelled'
        db.session.commit()
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'X',
            'items': '[{"product_id": ' + str(sample_product.id) + ', "quantity": 1}]',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 15000

    def test_idor_other_restaurant_404(self, client, db, sample_user, another_restaurant, sample_product):
        from app.models import Order, OrderItem
        foreign = Order(
            restaurant_id=another_restaurant.id,
            order_number='ORD-OTRO-EDIT',
            customer_name='Ajeno',
            status='pending',
            total=5000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add(foreign)
        db.session.flush()
        db.session.add(OrderItem(
            order_id=foreign.id,
            restaurant_id=another_restaurant.id,
            product_name=sample_product.name,
            product_price=5000,
            quantity=1,
            subtotal=5000,
        ))
        db.session.commit()
        self._login(client, sample_user)
        resp = client.get(f'/orders/{foreign.id}/edit')
        assert resp.status_code == 404


class TestUpdateOrderPaymentService:
    """update_order_payment: sobreescribir el pago al editar una venta."""

    def test_overwrite_cash_payment(self, db, order_with_items):
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        assert order_with_items.change_due == 5000

        OrderService.update_order_payment(order_with_items, 'cash', amount_received=30000)
        assert order_with_items.payment_method == 'cash'
        assert order_with_items.amount_received == 30000
        assert order_with_items.change_due == 15000

    def test_switch_method_from_cash_to_card(self, db, order_with_items):
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        OrderService.update_order_payment(order_with_items, 'card')
        assert order_with_items.payment_method == 'card'
        assert order_with_items.amount_received is None
        assert order_with_items.change_due is None

    def test_switch_to_nequi(self, db, order_with_items):
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        OrderService.update_order_payment(order_with_items, 'nequi')
        assert order_with_items.payment_method == 'nequi'

    def test_insufficient_cash_blocked(self, db, order_with_items):
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        with pytest.raises(PaymentValidationError):
            OrderService.update_order_payment(order_with_items, 'cash', amount_received=10000)
        assert order_with_items.amount_received == 20000

    def test_invalid_method_blocked(self, db, order_with_items):
        with pytest.raises(PaymentValidationError):
            OrderService.update_order_payment(order_with_items, 'bitcoin')

    def test_cancelled_order_blocked(self, db, order_with_items):
        order_with_items.status = 'cancelled'
        db.session.commit()
        with pytest.raises(PaymentValidationError):
            OrderService.update_order_payment(order_with_items, 'cash', amount_received=20000)


class TestEditWithPayment:
    """Edición de venta que además ajusta el pago (modal precargado)."""

    import re as _re

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _csrf_headers(self, client):
        page = client.get('/orders/')
        match = self._re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        assert match, 'no se encontró el token CSRF en /orders/'
        return {'X-CSRFToken': match.group(1)}

    def test_update_order_items_with_new_payment(self, db, order_with_items, sample_product):
        """Editar items + sobreescribir pago en un solo paso."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=15000)
        assert order_with_items.change_due == 0

        OrderService.update_order_items(
            order_with_items,
            self._items(sample_product, 2),
            sample_product.restaurant_id,
            payment_method='cash',
            amount_received=30000,
        )
        assert order_with_items.total == 10000
        assert order_with_items.amount_received == 30000
        assert order_with_items.change_due == 20000

    def test_edit_without_payment_keeps_cash_change(self, db, order_with_items, sample_product):
        """Editar items sin tocar pago: recalcula el cambio del pago cash."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        OrderService.update_order_items(
            order_with_items,
            self._items(sample_product, 1),
            sample_product.restaurant_id,
        )
        assert order_with_items.total == 5000
        assert order_with_items.amount_received == 20000
        assert order_with_items.change_due == 15000

    def test_edit_payment_exceeds_received_blocked(self, db, order_with_items, sample_product):
        """Editar items sin tocar pago: subir total por encima de lo recibido falla."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=15000)
        with pytest.raises(PaymentValidationError):
            OrderService.update_order_items(
                order_with_items,
                self._items(sample_product, 5),
                sample_product.restaurant_id,
            )
        assert order_with_items.total == 15000

    @staticmethod
    def _items(product, qty):
        return [{'product_id': product.id, 'quantity': qty}]

    def test_post_edit_updates_payment(self, client, db, order_with_items, sample_user, sample_product):
        """POST /orders/<id>/edit con payment_method sobreescribe el pago."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=15000)
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'Cliente Edit',
            'items': '[{"product_id": ' + str(sample_product.id) + ', "quantity": 1}]',
            'payment_method': 'card',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 5000
        assert reloaded.payment_method == 'card'
        assert reloaded.amount_received is None

    def test_post_edit_without_payment_keeps_method(self, client, db, order_with_items, sample_user, sample_product):
        """POST sin payment_method mantiene el pago existente (cash recalculado)."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=20000)
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'Cliente Edit',
            'items': '[{"product_id": ' + str(sample_product.id) + ', "quantity": 1}]',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 5000
        assert reloaded.payment_method == 'cash'
        assert reloaded.amount_received == 20000
        assert reloaded.change_due == 15000

    def test_post_edit_cash_amount(self, client, db, order_with_items, sample_user, sample_product):
        """POST con efectivo y monto actualiza recibido + cambio."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=15000)
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'Cliente Edit',
            'items': '[{"product_id": ' + str(sample_product.id) + ', "quantity": 1}]',
            'payment_method': 'cash',
            'amount_received': '10000',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 5000
        assert reloaded.amount_received == 10000
        assert reloaded.change_due == 5000

    def test_post_edit_insufficient_cash_redirects_error(self, client, db, order_with_items, sample_user, sample_product):
        """Efectivo insuficiente en edición → flash de error, pago intacto."""
        OrderService.record_payment(order_with_items, 'cash', amount_received=15000)
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post(f'/orders/{order_with_items.id}/edit', data={
            'customer_name': 'Cliente Edit',
            'items': '[{"product_id": ' + str(sample_product.id) + ', "quantity": 1}]',
            'payment_method': 'cash',
            'amount_received': '3000',
        }, headers=headers)
        assert resp.status_code == 302
        reloaded = db.session.get(Order, order_with_items.id)
        assert reloaded.total == 15000
        assert reloaded.amount_received == 15000
        assert reloaded.change_due == 0

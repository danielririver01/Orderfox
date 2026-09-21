"""Turnos de caja: apertura opcional + conteo físico obligatorio al cerrar.

Modo apagado (`require_cash_shift=False`) = flujo actual intacto.
Modo estricto = el efectivo exige turno abierto; el conteo solo se exige
al cerrar, sin fricción durante el día.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Order
from app.services.cash_register_service import (
    CashRegisterService,
    CashShiftService,
)
from app.services.order_service import OrderService, PaymentValidationError


@pytest.fixture
def shift_order(db, sample_restaurant):
    o = Order(
        restaurant_id=sample_restaurant.id,
        order_number='ORD-SHIFT-001',
        customer_name='Cliente Turno',
        customer_phone='+573001234567',
        status='pending',
        total=25000,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(o)
    db.session.commit()
    return o


def _enable_strict(db, restaurant):
    restaurant.require_cash_shift = True
    db.session.commit()


class TestStrictFlag:
    def test_default_off(self, sample_restaurant):
        assert sample_restaurant.require_cash_shift is False

    def test_mode_off_cash_without_shift_works(self, db, sample_restaurant, shift_order):
        order, _ = OrderService.record_payment(shift_order, 'cash', amount_received=25000)
        assert order.payment_method == 'cash'


class TestCashBlockedWithoutShift:
    def test_cash_blocked_in_strict_without_shift(self, db, sample_restaurant, shift_order):
        _enable_strict(db, sample_restaurant)
        with pytest.raises(PaymentValidationError) as exc:
            OrderService.record_payment(shift_order, 'cash', amount_received=25000)
        assert 'abrir caja' in str(exc.value).lower()
        assert exc.value.status_code == 409

    def test_digital_not_blocked_without_shift(self, db, sample_restaurant, shift_order):
        _enable_strict(db, sample_restaurant)
        order, _ = OrderService.record_payment(shift_order, 'nequi')
        assert order.payment_method == 'nequi'

    def test_open_then_cash_works(self, db, sample_restaurant, shift_order):
        _enable_strict(db, sample_restaurant)
        CashShiftService.open_shift(sample_restaurant.id, None, 50000)
        order, change = OrderService.record_payment(
            shift_order, 'cash', amount_received=30000)
        assert order.payment_method == 'cash'
        assert change == 5000


class TestShiftLifecycle:
    def test_double_open_rejected(self, db, sample_restaurant):
        CashShiftService.open_shift(sample_restaurant.id, None, 10000)
        with pytest.raises(ValueError) as exc:
            CashShiftService.open_shift(sample_restaurant.id, None, 5000)
        assert 'abierta' in str(exc.value).lower()

    def test_negative_opening_rejected(self, db, sample_restaurant):
        with pytest.raises(ValueError):
            CashShiftService.open_shift(sample_restaurant.id, None, -100)

    def test_close_requires_counted_in_strict(self, db, sample_restaurant):
        _enable_strict(db, sample_restaurant)
        CashShiftService.open_shift(sample_restaurant.id, None, 10000)
        with pytest.raises(ValueError) as exc:
            CashShiftService.close_shift(sample_restaurant.id, None, None)
        assert 'conteo' in str(exc.value).lower()

    def test_close_computes_difference(self, db, sample_restaurant, shift_order):
        _enable_strict(db, sample_restaurant)
        CashShiftService.open_shift(sample_restaurant.id, None, 50000)
        # Venta $25.000, recibe $30.000, vuelto $5.000.
        OrderService.record_payment(shift_order, 'cash', amount_received=30000)
        # Esperado = 50000 + 25000 - 5000 = 70000.
        assert CashShiftService.expected_cash_now(sample_restaurant.id) == 70000

        shift, closing = CashShiftService.close_shift(
            sample_restaurant.id, None, 68000)
        assert shift.status == 'closed'
        assert shift.expected_cash == 70000
        assert shift.counted_cash == 68000
        assert shift.difference == -2000
        # El snapshot del ticket guarda el arqueo.
        assert closing.opening_amount == 50000
        assert closing.expected_cash == 70000
        assert closing.counted_cash == 68000
        assert closing.difference == -2000
        assert closing.shift_id == shift.id

    def test_close_without_sales_allowed(self, db, sample_restaurant):
        _enable_strict(db, sample_restaurant)
        CashShiftService.open_shift(sample_restaurant.id, None, 40000)
        shift, closing = CashShiftService.close_shift(
            sample_restaurant.id, None, 40000)
        assert shift.difference == 0
        assert closing.total_sales == 0
        assert closing.expected_cash == 40000

    def test_close_without_shift_rejected(self, db, sample_restaurant):
        with pytest.raises(ValueError):
            CashShiftService.close_shift(sample_restaurant.id, None, 10000)


class TestPeriodCloseWithCounted:
    def test_period_close_requires_counted_in_strict(
            self, db, sample_restaurant, shift_order):
        # Se cobra en modo flexible y luego el admin activa el estricto.
        OrderService.record_payment(shift_order, 'cash', amount_received=30000)
        _enable_strict(db, sample_restaurant)
        start, end = CashRegisterService.resolve_range('today')
        with pytest.raises(ValueError) as exc:
            CashRegisterService.close_register(sample_restaurant.id, None, start, end)
        assert 'conteo' in str(exc.value).lower()

    def test_period_close_stores_arqueo(self, db, sample_restaurant, shift_order):
        OrderService.record_payment(shift_order, 'cash', amount_received=30000)
        _enable_strict(db, sample_restaurant)
        start, end = CashRegisterService.resolve_range('today')
        # Neto del periodo: 25000 - 5000 de vuelto = 20000.
        closing = CashRegisterService.close_register(
            sample_restaurant.id, None, start, end, counted_cash=19000)
        assert closing.expected_cash == 20000
        assert closing.counted_cash == 19000
        assert closing.difference == -1000

    def test_period_close_unchanged_when_off(
            self, db, sample_restaurant, shift_order):
        OrderService.record_payment(shift_order, 'cash', amount_received=25000)
        start, end = CashRegisterService.resolve_range('today')
        closing = CashRegisterService.close_register(
            sample_restaurant.id, None, start, end)
        assert closing.expected_cash is None
        assert closing.counted_cash is None


class TestShiftRoutes:
    """Rutas HTTP del turno + flag del admin + bloqueo en el cobro."""

    import re as _re

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _csrf_headers(self, client):
        page = client.get('/orders/')
        m = self._re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        token = m.group(1) if m else ''
        return {'X-CSRFToken': token}

    def test_open_status_close_flow(self, client, db, sample_restaurant, sample_user):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)

        opened = client.post('/cash-register/shift/open',
                             json={'opening_amount': 50000}, headers=headers)
        assert opened.status_code == 201
        assert opened.get_json()['data']['opening_amount'] == 50000

        status = client.get('/cash-register/api/shift')
        assert status.status_code == 200
        body = status.get_json()['data']
        assert body['open'] is True
        assert body['expected_cash'] == 50000

        closed = client.post('/cash-register/shift/close',
                             json={'counted_cash': 50000}, headers=headers)
        assert closed.status_code == 200
        data = closed.get_json()['data']
        assert data['difference'] == 0
        assert data['close_id'] is not None

        history = client.get('/cash-register/api/closes')
        assert history.status_code == 200
        assert any(c['counted_cash'] == 50000
                   for c in history.get_json()['data'])

    def test_settings_toggle(self, client, db, sample_restaurant, sample_user):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)

        current = client.get('/cash-register/api/settings')
        assert current.get_json()['data']['require_cash_shift'] is False

        enabled = client.put('/cash-register/api/settings',
                             json={'require_cash_shift': True}, headers=headers)
        assert enabled.status_code == 200
        assert enabled.get_json()['data']['require_cash_shift'] is True

        disabled = client.put('/cash-register/api/settings',
                              json={'require_cash_shift': False}, headers=headers)
        assert disabled.get_json()['data']['require_cash_shift'] is False

    def test_drawer_flags_default_off_and_persist(
            self, client, db, sample_restaurant, sample_user):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)

        current = client.get('/cash-register/api/settings')
        data = current.get_json()['data']
        assert data['drawer_enabled'] is False
        assert data['drawer_auto_open'] is False

        # Subconjunto: solo cajón, el modo estricto no se toca.
        updated = client.put('/cash-register/api/settings', json={
            'drawer_enabled': True, 'drawer_auto_open': True,
        }, headers=headers)
        assert updated.status_code == 200
        payload = updated.get_json()['data']
        assert payload['drawer_enabled'] is True
        assert payload['drawer_auto_open'] is True
        assert payload['require_cash_shift'] is False

        drawer = client.get('/cash-register/api/drawer')
        assert drawer.status_code == 200
        assert drawer.get_json()['data'] == {
            'drawer_enabled': True, 'drawer_auto_open': True,
        }

    def test_cash_payment_blocked_route_in_strict(
            self, client, db, sample_restaurant, sample_user, shift_order):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        client.put('/cash-register/api/settings',
                   json={'require_cash_shift': True}, headers=headers)

        blocked = client.post(f'/orders/{shift_order.id}/payment', json={
            'payment_method': 'cash', 'amount_received': 25000,
        }, headers=headers)
        assert blocked.status_code == 409
        assert 'abrir caja' in blocked.get_json()['error'].lower()

        # Digital no se bloquea.
        ok = client.post(f'/orders/{shift_order.id}/payment', json={
            'payment_method': 'nequi',
        }, headers=headers)
        assert ok.status_code == 200

    def test_period_close_requires_counted_route_in_strict(
            self, client, db, sample_restaurant, sample_user, shift_order):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        # Cobro en flexible, luego se activa el estricto.
        paid = client.post(f'/orders/{shift_order.id}/payment', json={
            'payment_method': 'cash', 'amount_received': 30000,
        }, headers=headers)
        assert paid.status_code == 200
        client.put('/cash-register/api/settings',
                   json={'require_cash_shift': True}, headers=headers)

        missing = client.post('/cash-register/close', json={'range': 'today'},
                              headers=headers)
        assert missing.status_code == 400
        assert 'conteo' in missing.get_json()['error'].lower()

        with_count = client.post('/cash-register/close',
                                 json={'range': 'today', 'counted_cash': 19000},
                                 headers=headers)
        assert with_count.status_code == 200

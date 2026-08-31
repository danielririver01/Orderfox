"""
Tests de trazabilidad completa de pedidos (OrderEvent, v1.4.0).

Cubre los casos aprobados:
1. Crear pedido como mesero → order_created con actor_role='waiter'.
2. Cambiar estado → status_changed con metadata {from, to}.
3. Cobrar como cajero → payment_registered con actor_role='cashier'.
4. Pedido del menú web → order_created con actor_role='customer'.
5. Expiración → order_expired con actor_role='system'.
6. Centro de Caja muestra creador y cobrador correctamente.
7. Detalle de pedido muestra historial cronológico completo.
8. Pedido sin eventos → "Sin registro previo" sin error.
9. CASCADE: eliminar pedido elimina sus eventos.
10. Ticket impreso NO contiene nombres de empleados.
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Category, Order, OrderEvent, Product, Restaurant, User
from app.services.cash_register_service import CashRegisterService
from app.services.employee_service import EmployeeService
from app.services.order_service import OrderService, log_event

# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def trace_restaurant(db):
    """Restaurante plan élite (empleados ilimitados) para trazabilidad."""
    r = Restaurant(
        name='Trace Restaurant',
        slug='trace-restaurant',
        whatsapp_phone='+573001111111',
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
def owner_user(db, trace_restaurant):
    u = User(
        restaurant_id=trace_restaurant.id,
        username='Owner Trace',
        email='trace-owner@test.com',
        password='x',
        role='owner',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def waiter_user(db, trace_restaurant):
    return EmployeeService.create_employee(trace_restaurant, 'Mesero Trace', 'waiter', '3847')


@pytest.fixture
def cashier_user(db, trace_restaurant):
    return EmployeeService.create_employee(trace_restaurant, 'Cajero Trace', 'cashier', '5926')


@pytest.fixture
def trace_product(db, trace_restaurant):
    cat = Category(
        restaurant_id=trace_restaurant.id, name='Comidas', sort_order=1, is_active=True,
    )
    db.session.add(cat)
    db.session.flush()
    p = Product(
        restaurant_id=trace_restaurant.id, category_id=cat.id,
        name='Hamburguesa Traza', price=15000, is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _make_order(db, restaurant, status='pending', order_number='TR-001'):
    o = Order(
        restaurant_id=restaurant.id,
        order_number=order_number,
        customer_name='Cliente Traza',
        customer_phone='+57300112233',
        status=status,
        total=39000,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(o)
    db.session.commit()
    return o


def _paid_order(db, restaurant, order_number='TR-PAID'):
    o = _make_order(db, restaurant, status='delivered', order_number=order_number)
    o.payment_method = 'cash'
    o.amount_received = 50000
    o.change_due = 11000
    o.paid_at = datetime.now(timezone.utc)
    db.session.commit()
    return o


def _csrf_headers(client, url):
    """Extrae el token CSRF de una página de la sesión activa (patrón del repo)."""
    page = client.get(url)
    m = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
    assert m, f'no se encontró el token CSRF en {url}'
    return {'X-CSRFToken': m.group(1)}


# ── Caso 1: mesero crea pedido ─────────────────────────────────────────────

class TestWaiterCreatesOrder:

    def test_waiter_order_created_event(self, client, db, trace_restaurant,
                                        waiter_user, trace_product):
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        headers = _csrf_headers(client, f'/empleado/{trace_restaurant.slug}/pedidos')
        resp = client.post(f'/empleado/{trace_restaurant.slug}/pedidos/nuevo', data={
            'items': json.dumps([{'product_id': trace_product.id, 'quantity': 2}]),
            'customer_name': 'Cliente Mesero',
        }, headers=headers)

        assert resp.status_code == 302, resp.get_data(as_text=True)
        order = Order.query.filter_by(restaurant_id=trace_restaurant.id).first()
        assert order is not None
        ev = OrderEvent.query.filter_by(order_id=order.id, event_type='order_created').first()
        assert ev is not None
        assert ev.actor_id == waiter_user.id
        assert ev.actor_role == 'waiter'


# ── Caso 2: cambio de estado ───────────────────────────────────────────────

class TestChangeStatus:

    def test_change_status_logs_event(self, client, db, trace_restaurant, owner_user):
        order = _make_order(db, trace_restaurant)
        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.id

        headers = _csrf_headers(client, '/orders/')
        resp = client.patch(f'/orders/{order.id}/status', json={'status': 'confirmed'},
                            headers=headers)
        assert resp.status_code == 200

        ev = OrderEvent.query.filter_by(order_id=order.id, event_type='status_changed').first()
        assert ev is not None
        assert ev.event_data == {'from': 'pending', 'to': 'confirmed'}
        assert ev.actor_id == owner_user.id
        assert ev.actor_role == 'owner'


# ── Caso 3: cajero cobra ───────────────────────────────────────────────────

class TestCashierPayment:

    def test_cashier_payment_logs_event(self, client, db, trace_restaurant,
                                        cashier_user):
        order = _make_order(db, trace_restaurant, status='confirmed')
        with client.session_transaction() as sess:
            sess['employee_id'] = cashier_user.id
            sess['employee_login'] = True

        headers = _csrf_headers(client, f'/empleado/{trace_restaurant.slug}/caja')
        resp = client.post(f'/orders/{order.id}/payment', json={
            'payment_method': 'cash',
            'amount_received': 50000,
        }, headers=headers)
        assert resp.status_code == 200, resp.get_data(as_text=True)

        ev = OrderEvent.query.filter_by(order_id=order.id,
                                        event_type='payment_registered').first()
        assert ev is not None
        assert ev.actor_id == cashier_user.id
        assert ev.actor_role == 'cashier'
        assert ev.event_data == {'method': 'cash', 'amount': 50000}


# ── Caso 4: pedido del menú web ────────────────────────────────────────────

class TestWebMenuOrder:

    def test_web_menu_order_logs_customer(self, client, db, sample_restaurant,
                                          sample_category, sample_product):
        with client.session_transaction() as sess:
            sess['checkout_start_time'] = time.time() - 5

        resp = client.post('/menu/api/order', json={
            'restaurant_id': sample_restaurant.id,
            'cart': {sample_product.id: {'quantity': 1, 'extras': []}},
            'customer_name': 'Cliente Web',
            'customer_phone': '+573001234567',
        })
        assert resp.status_code == 200, resp.get_data(as_text=True)

        order = Order.query.filter_by(restaurant_id=sample_restaurant.id).first()
        ev = OrderEvent.query.filter_by(order_id=order.id, event_type='order_created').first()
        assert ev is not None
        assert ev.actor_id is None
        assert ev.actor_role == 'customer'


# ── Caso 5: expiración automática ──────────────────────────────────────────

class TestExpiry:

    def test_expiry_logs_system_event(self, db, sample_restaurant):
        order = _make_order(db, sample_restaurant)
        order.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()

        from app.tasks import _perform_expiry
        _perform_expiry()

        db.session.refresh(order)
        assert order.status == 'expired'
        ev = OrderEvent.query.filter_by(order_id=order.id, event_type='order_expired').first()
        assert ev is not None
        assert ev.actor_id is None
        assert ev.actor_role == 'system'


# ── Caso 6: Centro de Caja muestra creador y cobrador ──────────────────────

class TestCashRegisterDisplay:

    def test_paid_orders_include_creator_and_cashier(self, db, trace_restaurant,
                                                     waiter_user, cashier_user):
        order = _paid_order(db, trace_restaurant)
        log_event(order.id, 'order_created', actor_id=waiter_user.id,
                  actor_role=waiter_user.role)
        log_event(order.id, 'payment_registered', actor_id=cashier_user.id,
                  actor_role=cashier_user.role,
                  metadata={'method': 'cash', 'amount': 50000})
        db.session.commit()

        start, end = CashRegisterService.resolve_range('today')
        orders = CashRegisterService.get_paid_orders(trace_restaurant.id, start, end)
        assert len(orders) == 1
        o = orders[0]
        assert o['created_by']['name'] == waiter_user.username
        assert o['created_by']['role_label'] == 'Mesero'
        assert o['paid_by']['name'] == cashier_user.username
        assert o['paid_by']['role_label'] == 'Cajero'
        assert o['created_by']['time'] is not None
        assert o['paid_by']['time'] is not None


# ── Caso 7: detalle de pedido con historial completo ───────────────────────

class TestOrderDetailHistory:

    def test_detail_shows_chronological_history(self, client, db, trace_restaurant,
                                                owner_user, waiter_user, cashier_user):
        order = _paid_order(db, trace_restaurant)
        log_event(order.id, 'order_created', actor_id=waiter_user.id,
                  actor_role=waiter_user.role)
        log_event(order.id, 'status_changed', actor_id=waiter_user.id,
                  actor_role=waiter_user.role,
                  metadata={'from': 'pending', 'to': 'confirmed'})
        log_event(order.id, 'payment_registered', actor_id=cashier_user.id,
                  actor_role=cashier_user.role,
                  metadata={'method': 'cash', 'amount': 50000})
        db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.id

        resp = client.get(f'/orders/{order.id}')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert 'Historial del pedido' in html
        assert 'Pedido creado' in html
        assert 'Confirmado' in html
        assert 'Cobrado — Efectivo $50.000' in html
        assert waiter_user.username in html
        assert 'Mesero' in html
        assert cashier_user.username in html
        assert 'Cajero' in html

    def test_order_without_events_shows_fallback(self, client, db, trace_restaurant,
                                                 owner_user):
        order = _make_order(db, trace_restaurant)
        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.id

        resp = client.get(f'/orders/{order.id}')
        assert resp.status_code == 200
        assert 'Sin registro previo a la implementación' in resp.get_data(as_text=True)


# ── Caso 9: CASCADE ────────────────────────────────────────────────────────

class TestCascadeDelete:

    def test_delete_order_removes_events(self, db, trace_restaurant, waiter_user):
        order = _paid_order(db, trace_restaurant)
        log_event(order.id, 'order_created', actor_id=waiter_user.id,
                  actor_role=waiter_user.role)
        db.session.commit()
        assert OrderEvent.query.filter_by(order_id=order.id).count() == 1

        ok, _ = OrderService.delete_order(order)
        assert ok is True
        assert OrderEvent.query.filter_by(order_id=order.id).count() == 0


# ── Caso 10: ticket impreso sin nombres de empleados ───────────────────────

class TestPrintedTicket:

    def test_ticket_template_has_no_employee_names(self):
        from pathlib import Path
        template = Path(__file__).resolve().parents[1] / \
            'app/template/dashboard/cash_register_print.html'
        content = template.read_text(encoding='utf-8')
        assert 'username' not in content
        assert 'closed_by' not in content

    def test_printed_close_ticket_omits_names(self, client, db, trace_restaurant,
                                              owner_user):
        _paid_order(db, trace_restaurant)
        start, end = CashRegisterService.resolve_range('today')
        closing = CashRegisterService.close_register(
            trace_restaurant.id, owner_user.id, start, end)

        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.id

        html = client.get(f'/cash-register/close/{closing.id}/print').get_data(as_text=True)
        assert owner_user.username not in html
        assert 'Cajero Trace' not in html
        assert 'Mesero Trace' not in html
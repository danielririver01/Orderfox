"""
Tests del Centro de Caja (cash register).

Cubre:
- Service: resolve_range (límites Colombia), get_summary (basado en paid_at,
  excluye cancelled/sin pago), desglose por método, get_pending, close_register
  (crea, bloquea duplicado exacto, bloquea solapamiento parcial, permite rango
  posterior), get_closes, get_close.
- Routes: página, api/summary, api/orders, api/pending, api/closes, POST /close
  (éxito + 409), print, IDOR.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import CashRegister, Order, Restaurant
from app.services.cash_register_service import CashRegisterService, NoSalesError
from app.utils.timezone import today_start_utc

# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def another_restaurant(db):
    """Segundo restaurante (para tests anti-IDOR)."""
    r = Restaurant(
        name='Otra Cafetería',
        slug='otra-cafeteria',
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


@pytest.fixture
def paid_order_factory(db, sample_restaurant):
    """Crea pedidos pagados con paid_at controlado (UTC)."""
    counter = {'n': 0}

    def _make(total, method, paid_at, status='delivered', amount_received=None,
              change_due=None, customer_name=None, restaurant_id=None):
        counter['n'] += 1
        o = Order(
            restaurant_id=restaurant_id or sample_restaurant.id,
            order_number=f'CR-{counter["n"]:04d}',
            customer_name=customer_name or 'Cliente Caja',
            status=status,
            total=total,
            payment_method=method,
            amount_received=amount_received,
            change_due=change_due,
            paid_at=paid_at,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add(o)
        db.session.commit()
        return o

    return _make


# ── Service: resolve_range ─────────────────────────────────────────────────

class TestResolveRange:
    """Rangos de fechas en hora de Colombia (UTC-5), end exclusivo."""

    def test_today_bounds(self):
        start, end = CashRegisterService.resolve_range('today')
        today = today_start_utc()
        assert start == today
        assert end == today + timedelta(days=1)

    def test_yesterday_bounds(self):
        start, end = CashRegisterService.resolve_range('yesterday')
        today = today_start_utc()
        assert start == today - timedelta(days=1)
        assert end == today

    def test_last_7_bounds(self):
        start, end = CashRegisterService.resolve_range('last_7')
        today = today_start_utc()
        assert start == today - timedelta(days=6)
        assert end == today + timedelta(days=1)

    def test_last_30_bounds(self):
        start, end = CashRegisterService.resolve_range('last_30')
        today = today_start_utc()
        assert start == today - timedelta(days=29)
        assert end == today + timedelta(days=1)

    def test_this_year_bounds(self):
        start, end = CashRegisterService.resolve_range('this_year')
        assert start.month == 1 and start.day == 1
        assert end > start

    def test_last_month_bounds(self):
        start, end = CashRegisterService.resolve_range('last_month')
        today = today_start_utc()
        # end == 1° de este mes (medianoche Bogotá)
        assert end.day == 1
        # start == 1° del mes anterior
        assert start.day == 1
        assert start < end
        assert end <= today + timedelta(days=1)

    def test_custom_bounds_colombia(self):
        # 2026-08-03 00:00 Bogotá == 2026-08-03 05:00 UTC
        start, end = CashRegisterService.resolve_range(
            'custom', from_date='2026-08-03', to_date='2026-08-03')
        assert start == datetime(2026, 8, 3, 5, 0)  # noqa: DTZ001
        assert end == datetime(2026, 8, 4, 5, 0)  # noqa: DTZ001

    def test_custom_missing_dates_raises(self):
        with pytest.raises(ValueError):
            CashRegisterService.resolve_range('custom')

    def test_custom_reversed_dates_raises(self):
        with pytest.raises(ValueError):
            CashRegisterService.resolve_range(
                'custom', from_date='2026-08-05', to_date='2026-08-03')

    def test_invalid_custom_format_raises(self):
        with pytest.raises(ValueError):
            CashRegisterService.resolve_range(
                'custom', from_date='no-es-fecha', to_date='2026-08-03')


# ── Service: get_summary ───────────────────────────────────────────────────

class TestGetSummary:
    """Totales basados en paid_at, excluyendo cancelled y sin pago."""

    def test_counts_only_paid_orders_in_range(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(25000, 'cash', now, amount_received=30000, change_due=5000)
        paid_order_factory(15000, 'nequi', now)

        # Pedido de ayer → fuera del rango "hoy"
        paid_order_factory(99999, 'card', now - timedelta(days=1))

        start, end = CashRegisterService.resolve_range('today')
        summary = CashRegisterService.get_summary(sample_restaurant.id, start, end)

        assert summary['total_sales'] == 40000
        assert summary['total_orders'] == 2
        assert summary['avg_ticket'] == 20000

    def test_excludes_cancelled_orders(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, status='cancelled', amount_received=10000)
        paid_order_factory(5000, 'card', now)

        start, end = CashRegisterService.resolve_range('today')
        summary = CashRegisterService.get_summary(sample_restaurant.id, start, end)
        assert summary['total_sales'] == 5000
        assert summary['total_orders'] == 1

    def test_excludes_orders_without_payment(self, db, sample_restaurant):
        o = Order(
            restaurant_id=sample_restaurant.id,
            order_number='CR-NOPAY',
            customer_name='Sin pago',
            status='pending',
            total=5000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add(o)
        db.session.commit()

        start, end = CashRegisterService.resolve_range('today')
        summary = CashRegisterService.get_summary(sample_restaurant.id, start, end)
        assert summary['total_sales'] == 0
        assert summary['total_orders'] == 0

    def test_breakdown_by_method(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        paid_order_factory(20000, 'cash', now, amount_received=20000)
        paid_order_factory(30000, 'nequi', now)
        paid_order_factory(40000, 'bancolombia', now)
        paid_order_factory(50000, 'card', now)

        start, end = CashRegisterService.resolve_range('today')
        summary = CashRegisterService.get_summary(sample_restaurant.id, start, end)
        b = summary['breakdown']

        assert b['cash'] == {'total': 30000, 'orders': 2}
        assert b['nequi'] == {'total': 30000, 'orders': 1}
        assert b['bancolombia'] == {'total': 40000, 'orders': 1}
        assert b['card'] == {'total': 50000, 'orders': 1}
        assert summary['total_sales'] == 150000
        assert summary['total_orders'] == 5

    def test_cash_change_total(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(25000, 'cash', now, amount_received=50000, change_due=25000)
        paid_order_factory(10000, 'cash', now, amount_received=20000, change_due=10000)
        paid_order_factory(10000, 'nequi', now)

        start, end = CashRegisterService.resolve_range('today')
        summary = CashRegisterService.get_summary(sample_restaurant.id, start, end)
        assert summary['cash_change_total'] == 35000

    def test_empty_range_returns_zeros(self, db, sample_restaurant):
        start, end = CashRegisterService.resolve_range('custom',
                                                        from_date='2000-01-01',
                                                        to_date='2000-01-01')
        summary = CashRegisterService.get_summary(sample_restaurant.id, start, end)
        assert summary['total_sales'] == 0
        assert summary['total_orders'] == 0
        assert summary['avg_ticket'] == 0
        assert summary['cash_change_total'] == 0


# ── Service: get_paid_orders / get_pending ────────────────────────────────

class TestGetPaidOrders:

    def test_filter_by_method(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        paid_order_factory(20000, 'card', now)

        start, end = CashRegisterService.resolve_range('today')
        orders = CashRegisterService.get_paid_orders(
            sample_restaurant.id, start, end, method='card')
        assert len(orders) == 1
        assert orders[0]['total'] == 20000
        assert orders[0]['payment_method'] == 'card'

    def test_search_by_order_number(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        o1 = paid_order_factory(10000, 'cash', now, amount_received=10000)

        start, end = CashRegisterService.resolve_range('today')
        orders = CashRegisterService.get_paid_orders(
            sample_restaurant.id, start, end, search=o1.order_number)
        assert len(orders) == 1
        assert orders[0]['id'] == o1.id

    def test_search_by_customer(self, db, sample_restaurant, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000,
                           customer_name='Cliente Especial X')

        start, end = CashRegisterService.resolve_range('today')
        orders = CashRegisterService.get_paid_orders(
            sample_restaurant.id, start, end, search='Especial')
        assert len(orders) == 1
        assert orders[0]['customer_name'] == 'Cliente Especial X'


class TestGetPending:

    def test_returns_unpaid_active_orders(self, db, sample_restaurant):
        now = datetime.now(timezone.utc)
        o1 = Order(restaurant_id=sample_restaurant.id, order_number='PEND-1',
                   customer_name='A', status='pending', total=10000,
                   expires_at=now + timedelta(hours=24))
        o2 = Order(restaurant_id=sample_restaurant.id, order_number='PEND-2',
                   customer_name='B', status='confirmed', total=20000,
                   expires_at=now + timedelta(hours=24))
        paid = Order(restaurant_id=sample_restaurant.id, order_number='PEND-3',
                     customer_name='C', status='delivered', total=30000,
                     payment_method='cash', paid_at=now,
                     expires_at=now + timedelta(hours=24))
        db.session.add_all([o1, o2, paid])
        db.session.commit()

        pending = CashRegisterService.get_pending(sample_restaurant.id)
        ids = {p['id'] for p in pending}
        assert ids == {o1.id, o2.id}


# ── Service: close_register ───────────────────────────────────────────────

class TestCloseRegister:

    def test_creates_snapshot(self, db, sample_restaurant, paid_order_factory, sample_user):
        now = datetime.now(timezone.utc)
        paid_order_factory(25000, 'cash', now, amount_received=50000, change_due=25000)
        paid_order_factory(15000, 'nequi', now)

        start, end = CashRegisterService.resolve_range('today')
        closing = CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)

        assert closing.total_sales == 40000
        assert closing.total_orders == 2
        assert closing.avg_ticket == 20000
        assert closing.cash_total == 25000
        assert closing.nequi_total == 15000
        assert closing.cash_change_total == 25000
        assert closing.closed_by == sample_user.id
        assert closing.period_start == start.replace(tzinfo=timezone.utc)
        assert closing.period_end == end.replace(tzinfo=timezone.utc)

    def test_blocks_exact_duplicate(self, db, sample_restaurant, paid_order_factory, sample_user):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)

        start, end = CashRegisterService.resolve_range('today')
        CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)

        with pytest.raises(ValueError) as exc:
            CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)
        assert 'Ya cerraste caja' in str(exc.value)
        assert '05:00' not in str(exc.value)  # no debe filtrarse hora UTC cruda

    def test_overlap_message_uses_colombia_date(self, db, sample_restaurant,
                                                paid_order_factory, sample_user):
        """El mensaje de error debe mostrar la fecha en hora de Colombia (UTC-5)."""
        # 2026-08-03 05:00 UTC == 2026-08-03 00:00 Bogotá
        base_utc = datetime(2026, 8, 3, 5, 0)  # noqa: DTZ001
        paid_order_factory(10000, 'cash', base_utc, amount_received=10000)

        start, end = base_utc, base_utc + timedelta(hours=24)
        CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)

        with pytest.raises(ValueError) as exc:
            CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)
        assert '03/08/2026' in str(exc.value)

    def test_blocks_partial_overlap(self, db, sample_restaurant, paid_order_factory, sample_user):
        """Cierre existente 9am–5pm; intento 3pm–6pm → rechazado."""
        base = datetime(2026, 8, 3, 14, 0)  # 9am Bogotá == 14:00 UTC  # noqa: DTZ001
        paid_order_factory(10000, 'cash', base, amount_received=10000)

        start, end = base, base + timedelta(hours=8)
        CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)

        overlap_start, overlap_end = base + timedelta(hours=6), base + timedelta(hours=9)
        with pytest.raises(ValueError) as exc:
            CashRegisterService.close_register(
                sample_restaurant.id, sample_user.id, overlap_start, overlap_end)
        assert 'Ya cerraste caja' in str(exc.value)

    def test_allows_non_overlapping_followup(self, db, sample_restaurant, paid_order_factory, sample_user):
        """Cierre 9am–5pm; cierre posterior 5pm–6pm → permitido (con venta en ese rango)."""
        base = datetime(2026, 8, 3, 14, 0)  # noqa: DTZ001
        paid_order_factory(10000, 'cash', base, amount_received=10000)

        start, end = base, base + timedelta(hours=8)
        CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)

        next_start, next_end = end, end + timedelta(hours=1)
        paid_order_factory(20000, 'nequi', end + timedelta(minutes=1))
        closing2 = CashRegisterService.close_register(
            sample_restaurant.id, sample_user.id, next_start, next_end)
        assert closing2.period_start == next_start.replace(tzinfo=timezone.utc)
        assert closing2.total_sales == 20000

    def test_rollback_on_failure_keeps_db_clean(self, db, sample_restaurant, sample_user):
        """Un cierre que falla (sin ventas) no debe dejar filas a medio insertar."""
        start, end = CashRegisterService.resolve_range('today')
        # Sin ventas → el cierre se rechaza y la DB queda limpia.
        with pytest.raises(ValueError) as exc:
            CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)
        assert 'No hay ventas' in str(exc.value)
        assert CashRegister.query.filter_by(restaurant_id=sample_restaurant.id).count() == 0

    def test_blocks_close_with_no_sales(self, db, sample_restaurant, sample_user):
        """No se puede cerrar caja en un periodo sin ventas (total $0)."""
        start, end = CashRegisterService.resolve_range('today')
        with pytest.raises(NoSalesError) as exc:
            CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)
        assert 'No hay ventas' in str(exc.value)

    def test_allows_close_with_sales(self, db, sample_restaurant, sample_user, paid_order_factory):
        """Con ventas en el periodo el cierre sí procede."""
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        start, end = CashRegisterService.resolve_range('today')
        closing = CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)
        assert closing.total_sales == 10000
        assert closing.total_orders == 1


# ── Routes ─────────────────────────────────────────────────────────────────

class TestCashRegisterRoutes:
    """Tests de rutas web + API del Centro de Caja."""

    import re as _re

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _csrf_headers(self, client):
        page = client.get('/cash-register/')
        match = self._re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        assert match, 'no se encontró el token CSRF en /cash-register/'
        return {'X-CSRFToken': match.group(1)}

    def test_index_renders(self, client, db, sample_user):
        self._login(client, sample_user)
        resp = client.get('/cash-register/')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Centro de Caja' in body

    def test_api_summary(self, client, db, sample_restaurant, sample_user, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        self._login(client, sample_user)

        resp = client.get('/cash-register/api/summary?range=today')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['total_sales'] == 10000
        assert body['data']['breakdown']['cash']['orders'] == 1

    def test_api_summary_bad_range(self, client, db, sample_user):
        self._login(client, sample_user)
        resp = client.get('/cash-register/api/summary?range=whatever')
        assert resp.status_code == 400

    def test_api_orders_filter(self, client, db, sample_restaurant, sample_user, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        paid_order_factory(20000, 'card', now)
        self._login(client, sample_user)

        resp = client.get('/cash-register/api/orders?range=today&method=card')
        assert resp.status_code == 200
        orders = resp.get_json()['data']
        assert len(orders) == 1
        assert orders[0]['payment_method'] == 'card'

    def test_api_pending(self, client, db, sample_restaurant, sample_user):
        now = datetime.now(timezone.utc)
        o = Order(restaurant_id=sample_restaurant.id, order_number='PEND-R',
                  customer_name='X', status='pending', total=10000,
                  expires_at=now + timedelta(hours=24))
        db.session.add(o)
        db.session.commit()
        self._login(client, sample_user)

        resp = client.get('/cash-register/api/pending')
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) == 1

    def test_api_closes_empty(self, client, db, sample_user):
        self._login(client, sample_user)
        resp = client.get('/cash-register/api/closes')
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

    def test_post_close_success(self, client, db, sample_restaurant, sample_user,
                                paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        self._login(client, sample_user)
        headers = self._csrf_headers(client)

        resp = client.post('/cash-register/close', json={'range': 'today'}, headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['id'] > 0

    def test_post_close_overlap_409(self, client, db, sample_restaurant, sample_user,
                                    paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)
        self._login(client, sample_user)
        headers = self._csrf_headers(client)

        first = client.post('/cash-register/close', json={'range': 'today'}, headers=headers)
        assert first.status_code == 200

        second = client.post('/cash-register/close', json={'range': 'today'}, headers=headers)
        assert second.status_code == 409
        body = second.get_json()
        assert body['success'] is False
        assert body['error']

    def test_post_close_bad_range_400(self, client, db, sample_user):
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post('/cash-register/close', json={'range': 'nope'}, headers=headers)
        assert resp.status_code == 400

    def test_post_close_no_sales_400(self, client, db, sample_user):
        """Sin ventas en el periodo → el cierre se rechaza con 400."""
        self._login(client, sample_user)
        headers = self._csrf_headers(client)
        resp = client.post('/cash-register/close', json={'range': 'today'}, headers=headers)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert 'No hay ventas' in body['error']

    def test_print_close(self, client, db, sample_restaurant, sample_user, paid_order_factory):
        now = datetime.now(timezone.utc)
        paid_order_factory(25000, 'cash', now, amount_received=50000, change_due=25000)
        start, end = CashRegisterService.resolve_range('today')
        closing = CashRegisterService.close_register(sample_restaurant.id, sample_user.id, start, end)
        self._login(client, sample_user)

        resp = client.get(f'/cash-register/close/{closing.id}/print')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Cierre de Caja' in body
        assert '25.000' in body

    def test_print_close_idor_404(self, client, db, another_restaurant,
                                  sample_user):
        """Un cierre de OTRO restaurante no debe ser visible (404)."""
        now = datetime.now(timezone.utc)
        foreign_order = Order(restaurant_id=another_restaurant.id,
                              order_number='FOREIGN-1', status='delivered', total=5000,
                              payment_method='cash', paid_at=now,
                              expires_at=now + timedelta(hours=24))
        db.session.add(foreign_order)
        db.session.commit()
        fstart, fend = CashRegisterService.resolve_range('today')
        foreign_close = CashRegisterService.close_register(
            another_restaurant.id, None, fstart, fend)

        self._login(client, sample_user)
        resp = client.get(f'/cash-register/close/{foreign_close.id}/print')
        assert resp.status_code == 404

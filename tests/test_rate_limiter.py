import pytest

from app.models import Order
from app.utils.rate_limiter import OrderRateLimiter

# Máquina de estados completa de pedidos (order_service.validate_status_transition).
ORDER_STATUSES = ['pending', 'confirmed', 'delivered', 'cancelled', 'expired']


def _order(restaurant_id, ip, status):
    # order_number es String(20): numeramos en vez de meter ip+status.
    _order.seq = getattr(_order, 'seq', 0) + 1
    return Order(
        restaurant_id=restaurant_id,
        order_number=f'ORD-RL{_order.seq:03d}',
        customer_name='Rate Limit Test',
        total=1000,
        status=status,
        ip_address=ip,
    )


class TestOrderRateLimiter:

    def test_get_recent_orders_count_zero_when_no_orders(self, db, sample_restaurant):
        count = OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '192.168.1.1', minutes=1
        )
        assert count == 0

    def test_get_recent_orders_count_with_matching_ip(self, db, sample_restaurant, sample_order):
        sample_order.ip_address = '192.168.1.1'
        db.session.commit()

        count = OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '192.168.1.1', minutes=1
        )
        assert count == 1

    def test_get_recent_orders_count_ignores_different_ip(self, db, sample_restaurant, sample_order):
        sample_order.ip_address = '192.168.1.1'
        db.session.commit()

        count = OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '192.168.1.2', minutes=1
        )
        assert count == 0

    def test_should_not_block_normal_request(self, db, sample_restaurant):
        should_block, msg, wait = OrderRateLimiter.should_block_request(
            sample_restaurant.id, '192.168.1.1'
        )
        assert should_block is False
        assert msg is None
        assert wait is None

    def test_is_ip_banned_returns_false_when_under_limit(self, db, sample_restaurant):
        banned = OrderRateLimiter.is_ip_banned(sample_restaurant.id, '192.168.1.1')
        assert banned is False

    def test_ip_address_stored_on_order(self, db, sample_restaurant):
        """Verifica que la IP se almacena en el campo ip_address de la orden."""
        from app.models import Order
        o = Order(
            restaurant_id=sample_restaurant.id,
            order_number='ORD-TEST-IP',
            customer_name='Test IP',
            total=1000,
            status='pending',
            ip_address='10.0.0.1',
        )
        db.session.add(o)
        db.session.commit()

        assert o.ip_address == '10.0.0.1'
        # Verify the rate limiter can find it by ip_address
        count = OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '10.0.0.1', minutes=1
        )
        assert count == 1

    def test_ip_address_detects_rate_limited_ips(self, db, sample_restaurant):
        """Verifica que órdenes con distintas IPs se cuentan correctamente."""
        # Create orders from two different IPs
        o1 = Order(
            restaurant_id=sample_restaurant.id,
            order_number='ORD-IP1',
            customer_name='IP1',
            total=1000,
            status='pending',
            ip_address='10.0.0.1',
        )
        o2 = Order(
            restaurant_id=sample_restaurant.id,
            order_number='ORD-IP2',
            customer_name='IP2',
            total=2000,
            status='pending',
            ip_address='10.0.0.2',
        )
        db.session.add_all([o1, o2])
        db.session.commit()

        count_ip1 = OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '10.0.0.1', minutes=1
        )
        count_ip2 = OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '10.0.0.2', minutes=1
        )
        assert count_ip1 == 1
        assert count_ip2 == 1


# ── R-06 / VLZ-8: 'completed' no existe y los estados de avanzar no contaban ─

class TestEveryStatusCounts:

    @pytest.mark.parametrize('status', ORDER_STATUSES)
    def test_order_in_any_status_counts(self, db, sample_restaurant, status):
        """Regresión de R-06: un pedido confirmado (o entregado, o cancelado)
        dentro de la ventana SÍ cuenta para el límite de 3/min."""
        db.session.add(_order(sample_restaurant.id, '10.0.0.9', status))
        db.session.commit()

        assert OrderRateLimiter.get_recent_orders_count(
            sample_restaurant.id, '10.0.0.9', minutes=1) == 1

    def test_confirmed_orders_trigger_the_burst_block(self, db, sample_restaurant):
        """El escenario exacto de R-06: el atacante cuyos pedidos se confirman
        rápido debe quedar bloqueado por el límite de ráfaga (3/min)."""
        for i in range(3):
            db.session.add(_order(sample_restaurant.id, '10.0.0.10', 'confirmed'))
        db.session.commit()

        should_block, _msg, wait = OrderRateLimiter.should_block_request(
            sample_restaurant.id, '10.0.0.10')
        assert should_block is True
        assert wait == 600

    def test_cancelling_spam_does_not_lift_the_ban(self, db, sample_restaurant):
        """Si el restaurante cancela el spam, las órdenes siguen contando:
        cancelar no puede convertirse en una vía para evadir el baneo."""
        for _ in range(3):
            db.session.add(_order(sample_restaurant.id, '10.0.0.11', 'cancelled'))
        db.session.commit()

        assert OrderRateLimiter.is_ip_banned(sample_restaurant.id, '10.0.0.11')

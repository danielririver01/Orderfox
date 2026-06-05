from datetime import datetime, timezone, timedelta
from app.utils.rate_limiter import OrderRateLimiter


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
        from app.models import Order
        import time as _time

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

import pytest
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from app.models import User, Restaurant, Category, Product, Table, DiscountCoupon
from app.services.auth_service import AuthService
from app.services.subscription_service import SubscriptionService
from app.services.dashboard_service import DashboardService
from app.services.order_service import OrderService
from app.services.category_service import CategoryService
from app.services.product_service import ProductService
from app.services.public_menu_service import PublicMenuService
from app.services.qr_service import QRService


class TestAuthService:
    def test_authenticate_success(self, sample_user):
        user, error = AuthService.authenticate('admin@test.com', 'TestPass123')
        assert user is not None
        assert user.id == sample_user.id
        assert error is None

    def test_authenticate_wrong_password(self, sample_user):
        user, error = AuthService.authenticate('admin@test.com', 'WrongPass')
        assert user is None
        assert error == {'error_code': 'INVALID_CREDENTIALS', 'message': 'Credenciales inválidas'}

    def test_authenticate_unknown_email(self, sample_user):
        user, error = AuthService.authenticate('unknown@test.com', 'TestPass123')
        assert user is None
        assert error == {'error_code': 'INVALID_CREDENTIALS', 'message': 'Credenciales inválidas'}

    def test_authenticate_none_email(self, sample_user):
        user, error = AuthService.authenticate(None, 'TestPass123')
        assert user is None
        assert error == {'error_code': 'INVALID_CREDENTIALS', 'message': 'Credenciales inválidas'}

    def test_get_user_by_id(self, sample_user):
        user = AuthService.get_user(sample_user.id)
        assert user is not None
        assert user.id == sample_user.id

    def test_get_user_not_found(self, db):
        user = AuthService.get_user(99999)
        assert user is None

    def test_get_user_none(self, db):
        user = AuthService.get_user(None)
        assert user is None


class TestDashboardService:
    def test_get_user_by_id(self, sample_user):
        user = DashboardService.get_user(sample_user.id)
        assert user is not None
        assert user.id == sample_user.id

    def test_get_user_not_found(self, db):
        user = DashboardService.get_user(99999)
        assert user is None

    def test_delete_restaurant(self, sample_restaurant, db):
        success, result = DashboardService.delete_restaurant(sample_restaurant)
        assert success is True
        assert Restaurant.query.get(sample_restaurant.id) is None

    def test_delete_restaurant_none(self, db):
        success, result = DashboardService.delete_restaurant(None)
        assert success is False

    def test_update_profile_name(self, sample_restaurant, sample_user, db):
        success, error = DashboardService.update_profile(
            sample_restaurant, sample_user,
            'New Name', '+573001234567', 'admin'
        )
        assert success is True
        assert error is None
        assert sample_restaurant.name == 'New Name'

    def test_update_profile_duplicate_name(self, db, sample_restaurant):
        other = Restaurant(
            name='Other Restaurant',
            slug='other-restaurant',
            whatsapp_phone='+573009999999',
            plan_type='emprendedor',
            is_active=True,
            subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.session.add(other)
        db.session.commit()
        success, error = DashboardService.update_profile(
            sample_restaurant, None,
            'Other Restaurant', '+573001234567', None
        )
        assert success is False

    def test_change_email_success(self, sample_user, db):
        success, message, status = DashboardService.change_email(
            sample_user, 'new@test.com', 'new@test.com'
        )
        assert success is True
        assert sample_user.email == 'new@test.com'

    def test_change_email_mismatch(self, sample_user, db):
        success, message, status = DashboardService.change_email(
            sample_user, 'new@test.com', 'different@test.com'
        )
        assert success is False
        assert status == 400

    def test_change_email_invalid(self, sample_user, db):
        success, message, status = DashboardService.change_email(
            sample_user, 'invalid', 'invalid'
        )
        assert success is False
        assert status == 400

    def test_change_email_empty(self, sample_user, db):
        success, message, status = DashboardService.change_email(
            sample_user, '', ''
        )
        assert success is False
        assert status == 400


class TestOrderService:
    def test_validate_table_found(self, sample_restaurant, db):
        table = Table(
            restaurant_id=sample_restaurant.id,
            name='Mesa 1',
            qr_code='qr-code-1',
        )
        db.session.add(table)
        db.session.commit()
        result = OrderService.validate_table(sample_restaurant.id, table.id)
        assert result is not None
        assert result.id == table.id

    def test_validate_table_not_found(self, sample_restaurant):
        result = OrderService.validate_table(sample_restaurant.id, 99999)
        assert result is None

    def test_validate_table_wrong_restaurant(self, sample_restaurant, db):
        other = Restaurant(
            name='Other', slug='other', whatsapp_phone='+573001111111',
            plan_type='emprendedor', is_active=True,
            subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.session.add(other)
        db.session.commit()
        table = Table(restaurant_id=other.id, name='Mesa', qr_code='qr')
        db.session.add(table)
        db.session.commit()
        result = OrderService.validate_table(sample_restaurant.id, table.id)
        assert result is None

    def test_get_active_products(self, sample_restaurant, sample_category, sample_product, db):
        active2 = Product(restaurant_id=sample_restaurant.id, category_id=sample_category.id,
                          name='Active 2', price=2000, is_active=True)
        db.session.add(active2)
        db.session.commit()
        products = OrderService.get_active_products(sample_restaurant.id)
        assert len(products) == 2
        assert all(p.is_active for p in products)

    def test_change_order_status(self, sample_order, db):
        updated = OrderService.change_order_status(sample_order, 'confirmed')
        assert updated.status == 'confirmed'

    def test_cancel_order_success(self, sample_order, db):
        success, error = OrderService.cancel_order(sample_order)
        assert success is True
        assert sample_order.status == 'cancelled'

    def test_cancel_order_delivered(self, sample_order, db):
        sample_order.status = 'delivered'
        db.session.commit()
        success, error = OrderService.cancel_order(sample_order)
        assert success is False

    def test_delete_order_success(self, sample_order, db):
        sample_order.status = 'cancelled'
        db.session.commit()
        success, error = OrderService.delete_order(sample_order)
        assert success is True

    def test_delete_order_not_cancelled(self, sample_order, db):
        success, error = OrderService.delete_order(sample_order)
        assert success is False


class TestCategoryService:
    def test_get_active_categories(self, sample_restaurant, sample_category, db):
        active = Category(restaurant_id=sample_restaurant.id, name='Active', sort_order=10, is_active=True)
        inactive = Category(restaurant_id=sample_restaurant.id, name='Inactive', sort_order=20, is_active=False)
        db.session.add_all([active, inactive])
        db.session.commit()
        cats = CategoryService.get_active_categories(sample_restaurant.id)
        assert len(cats) == 2
        assert all(c.is_active for c in cats)

    def test_get_active_categories_empty(self, sample_restaurant, db):
        cats = CategoryService.get_active_categories(sample_restaurant.id)
        assert len(cats) == 0


class TestProductService:
    def test_get_products_paginated_default(self, sample_restaurant, sample_category, sample_product, db):
        for i in range(7):
            db.session.add(Product(
                restaurant_id=sample_restaurant.id, category_id=sample_category.id,
                name=f'Product {i}', price=1000 * (i + 1), is_active=True
            ))
        db.session.commit()
        pagination = ProductService.get_products_paginated(sample_restaurant.id, sample_category.id)
        assert len(pagination.items) == 6
        assert pagination.total == 8
        assert pagination.pages == 2

    def test_get_products_paginated_page_2(self, sample_restaurant, sample_category, sample_product, db):
        for i in range(7):
            db.session.add(Product(
                restaurant_id=sample_restaurant.id, category_id=sample_category.id,
                name=f'Product {i}', price=1000 * (i + 1), is_active=True
            ))
        db.session.commit()
        pagination = ProductService.get_products_paginated(
            sample_restaurant.id, sample_category.id, page=2
        )
        assert len(pagination.items) == 2
        assert pagination.total == 8
        assert pagination.pages == 2

    def test_get_products_paginated_empty(self, sample_restaurant, sample_category, db):
        pagination = ProductService.get_products_paginated(sample_restaurant.id, sample_category.id)
        assert len(pagination.items) == 0
        assert pagination.total == 0


class TestPublicMenuService:
    def test_get_first_active_restaurant(self, db, sample_restaurant):
        r = PublicMenuService.get_first_active_restaurant()
        assert r is not None
        assert r.id == sample_restaurant.id
        assert r.is_active is True

    def test_get_first_active_restaurant_returns_first(self, db, sample_restaurant):
        r = PublicMenuService.get_first_active_restaurant()
        assert r is not None
        assert r.id == sample_restaurant.id

    def test_get_restaurant_by_id(self, sample_restaurant):
        r = PublicMenuService.get_restaurant_by_id(sample_restaurant.id)
        assert r is not None
        assert r.id == sample_restaurant.id

    def test_get_restaurant_by_id_not_found(self, db):
        r = PublicMenuService.get_restaurant_by_id(99999)
        assert r is None


class TestQRService:
    def test_generate_menu_qr_png(self):
        buf, mime = QRService.generate_menu_qr('https://example.com/menu')
        assert buf is not None
        assert mime == 'image/png'
        assert buf.getvalue()[:8] == b'\x89PNG\r\n\x1a\n'

    def test_generate_menu_qr_jpg(self):
        buf, mime = QRService.generate_menu_qr('https://example.com/menu', fmt='jpg')
        assert buf is not None
        assert mime == 'image/jpeg'
        assert buf.getvalue()[:2] == b'\xff\xd8'

    def test_generate_menu_qr_long_url(self):
        long_url = 'https://example.com/' + 'a' * 500
        buf, mime = QRService.generate_menu_qr(long_url)
        assert buf is not None
        assert mime == 'image/png'

    def test_generate_table_qr(self):
        buf = QRService.generate_table_qr('https://example.com/table/1')
        assert buf is not None
        assert buf.getvalue()[:8] == b'\x89PNG\r\n\x1a\n'

    def test_generate_table_qr_with_blur(self):
        buf = QRService.generate_table_qr('https://example.com/table/1', apply_blur=True)
        assert buf is not None
        assert buf.getvalue()[:8] == b'\x89PNG\r\n\x1a\n'

    def test_generate_table_qr_different_urls(self):
        buf1 = QRService.generate_table_qr('https://example.com/table/1')
        buf2 = QRService.generate_table_qr('https://example.com/table/2')
        assert buf1.getvalue() != buf2.getvalue()


class TestStreakService:
    def test_calculate_tier_all_cases(self):
        from app.services.streak_service import calculate_tier, TIER_NAMES
        cases = [
            (0, 0, None),
            (1, 1, 'Bronce'),
            (2, 1, 'Bronce'),
            (3, 2, 'Plata'),
            (5, 2, 'Plata'),
            (6, 3, 'Oro'),
            (11, 3, 'Oro'),
            (12, 4, 'Diamante'),
            (20, 4, 'Diamante'),
        ]
        for count, expected_tier, expected_name in cases:
            tier = calculate_tier(count)
            assert tier == expected_tier, (
                f'calculate_tier({count}) = {tier}, expected {expected_tier}'
            )
            name = TIER_NAMES.get(tier)
            assert name == expected_name, (
                f'TIER_NAMES[{tier}] = {name}, expected {expected_name}'
            )

    def test_bump_streak_idempotent(self, sample_restaurant):
        from app.services.streak_service import bump_streak

        payment_id = 'test_payment_123'
        first = bump_streak(sample_restaurant.id, payment_id)
        assert first['duplicate'] is False
        assert first['new_renewal_count'] == 1
        assert first['new_tier'] == 1

        second = bump_streak(sample_restaurant.id, payment_id)
        assert second['duplicate'] is True

        third = bump_streak(sample_restaurant.id, 'test_payment_456')
        assert third['duplicate'] is False
        assert third['new_renewal_count'] == 2

    def test_reset_streak_preserves_highest_tier(self, sample_restaurant):
        from app.services.streak_service import bump_streak, reset_streak, get_streak

        bump_streak(sample_restaurant.id, 'reset_test_1')
        bump_streak(sample_restaurant.id, 'reset_test_2')
        bump_streak(sample_restaurant.id, 'reset_test_3')

        before = get_streak(sample_restaurant.id)
        assert before['renewal_count'] == 3

        reset_streak(sample_restaurant.id)

        after = get_streak(sample_restaurant.id)
        assert after['renewal_count'] == 0

    def test_get_streak_no_streak(self, sample_restaurant):
        from app.services.streak_service import reset_streak, get_streak

        reset_streak(sample_restaurant.id)
        result = get_streak(sample_restaurant.id)
        assert result['tier'] == 0
        assert result['status'] == 'inactive'


class TestDiscountCoupon:
    def test_build_preference_applies_coupon(self, db, sample_restaurant, sample_coupon):
        data, info, coupon = SubscriptionService.build_mp_preference_data(
            'emprendedor', sample_restaurant.id, 'https://velzia.co'
        )
        assert coupon is not None
        assert coupon.id == sample_coupon.id
        unit_price = data['items'][0]['unit_price']
        expected = round(float(info['price_raw']) * 0.8, 2)
        assert unit_price == expected

    def test_build_preference_ignores_expired_coupon(self, db, sample_restaurant, expired_coupon):
        data, info, coupon = SubscriptionService.build_mp_preference_data(
            'emprendedor', sample_restaurant.id, 'https://velzia.co'
        )
        assert coupon is None
        unit_price = data['items'][0]['unit_price']
        assert unit_price == float(info['price_raw'])

    def test_reserve_coupon_sets_status(self, db, sample_restaurant, sample_coupon):
        SubscriptionService.reserve_coupon(sample_coupon, 'pref_test_123')
        db.session.commit()
        c = db.session.get(DiscountCoupon, sample_coupon.id)
        assert c.status == 'reserved'
        assert c.preference_id == 'pref_test_123'

    def test_reserve_releases_previous(self, db, sample_restaurant, sample_coupon):
        old = DiscountCoupon(
            restaurant_id=sample_restaurant.id,
            percentage=10,
            status='reserved',
            preference_id='pref_old',
            reserved_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.session.add(old)
        db.session.commit()

        SubscriptionService.reserve_coupon(sample_coupon, 'pref_new')

        old = db.session.get(DiscountCoupon, old.id)
        assert old.status == 'pending'
        assert old.preference_id is None

    def test_apply_coupon(self, db, sample_coupon):
        SubscriptionService.apply_coupon(sample_coupon, 'payment_999')
        db.session.commit()
        c = db.session.get(DiscountCoupon, sample_coupon.id)
        assert c.status == 'applied'
        assert c.applied_to_payment_id == 'payment_999'

    def test_fifo_picks_oldest_pending(self, db, sample_restaurant):
        c1 = DiscountCoupon(
            restaurant_id=sample_restaurant.id,
            percentage=10,
            status='pending',
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        c2 = DiscountCoupon(
            restaurant_id=sample_restaurant.id,
            percentage=20,
            status='pending',
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.session.add_all([c1, c2])
        db.session.commit()

        _, _, coupon = SubscriptionService.build_mp_preference_data(
            'emprendedor', sample_restaurant.id, 'https://velzia.co'
        )
        assert coupon.id == c1.id

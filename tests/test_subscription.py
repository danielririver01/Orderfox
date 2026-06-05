from datetime import datetime, timezone, timedelta
from app.models import Product
from app.utils.subscription import (
    is_subscription_active,
    get_subscription_status,
    can_perform_crud,
    check_feature_access,
    check_product_limit,
    sanitize_restaurant_limits,
    get_plan_limits,
)


class TestIsSubscriptionActive:

    def test_active_subscription(self, sample_restaurant):
        assert is_subscription_active(sample_restaurant) is True
        assert is_subscription_active(sample_restaurant, include_grace_period=True) is True

    def test_expired_subscription(self, expired_restaurant):
        assert is_subscription_active(expired_restaurant) is False
        assert is_subscription_active(expired_restaurant, include_grace_period=True) is False

    def test_grace_period_subscription(self, grace_period_restaurant):
        assert is_subscription_active(grace_period_restaurant) is False
        assert is_subscription_active(grace_period_restaurant, include_grace_period=True) is True

    def test_no_expiration_date(self, db):
        r = sample_restaurant = type('R', (), {
            'is_active': True,
            'subscription_expires_at': None
        })
        assert is_subscription_active(r) is False

    def test_inactive_restaurant(self, sample_restaurant):
        sample_restaurant.is_active = False
        assert is_subscription_active(sample_restaurant) is False

    def test_none_restaurant(self):
        assert is_subscription_active(None) is False


class TestGetSubscriptionStatus:

    def test_active_status(self, sample_restaurant):
        status = get_subscription_status(sample_restaurant)
        assert status['is_active'] is True
        assert status['status'] == 'active'
        assert status['can_crud'] is True
        assert status['plan'] == 'emprendedor'

    def test_expired_status(self, expired_restaurant):
        status = get_subscription_status(expired_restaurant)
        assert status['is_active'] is False
        assert status['status'] == 'expired'
        assert status['can_crud'] is False

    def test_grace_period_status(self, grace_period_restaurant):
        status = get_subscription_status(grace_period_restaurant)
        assert status['is_active'] is False
        assert status['status'] == 'grace_period'
        assert status['can_crud'] is False
        assert 'gracia' in status['message'].lower()

    def test_inactive_restaurant_status(self, sample_restaurant):
        sample_restaurant.is_active = False
        status = get_subscription_status(sample_restaurant)
        assert status['is_active'] is False
        assert status['status'] == 'inactive'

    def test_no_subscription_status(self, sample_restaurant):
        sample_restaurant.subscription_expires_at = None
        status = get_subscription_status(sample_restaurant)
        assert status['status'] == 'no_subscription'

    def test_none_restaurant_status(self):
        status = get_subscription_status(None)
        assert status['is_active'] is False
        assert status['status'] == 'not_found'

    def test_expiring_soon_neutral(self, db):
        r = _make_restaurant(days_until_expiry=6)
        status = get_subscription_status(r)
        assert status['is_active'] is True
        assert status['status'] == 'expiring_soon_neutral'
        assert status['days_remaining'] in (6, 7)

    def test_expiring_soon_warning(self, db):
        r = _make_restaurant(days_until_expiry=3)
        status = get_subscription_status(r)
        assert status['is_active'] is True
        assert status['status'] == 'expiring_soon_warning'

    def test_expiring_soon_urgent(self, db):
        r = _make_restaurant(days_until_expiry=1)
        status = get_subscription_status(r)
        assert status['is_active'] is True
        assert status['status'] == 'expiring_soon_urgent'


class TestCanPerformCrud:

    def test_active_can_crud(self, sample_restaurant):
        assert can_perform_crud(sample_restaurant) is True

    def test_expired_cannot_crud(self, expired_restaurant):
        assert can_perform_crud(expired_restaurant) is False

    def test_grace_period_cannot_crud(self, grace_period_restaurant):
        assert can_perform_crud(grace_period_restaurant) is False

    def test_none_restaurant(self):
        assert can_perform_crud(None) is False


class TestCheckFeatureAccess:

    def test_basic_feature_success(self, sample_restaurant):
        assert check_feature_access(sample_restaurant, 'has_qr') is True

    def test_feature_not_in_plan(self, sample_restaurant):
        assert check_feature_access(sample_restaurant, 'has_modifiers') is False

    def test_expired_restaurant(self, expired_restaurant):
        assert check_feature_access(expired_restaurant, 'has_qr') is False

    def test_none_restaurant(self):
        assert check_feature_access(None, 'has_qr') is False


class TestGetPlanLimits:

    def test_emprendedor_limits(self):
        limits = get_plan_limits('emprendedor')
        assert limits['max_products'] == 25
        assert limits['has_qr'] is True
        assert limits['has_modifiers'] is False

    def test_crecimiento_limits(self):
        limits = get_plan_limits('crecimiento')
        assert limits['max_products'] == 100
        assert limits['has_table_qr'] is True
        assert limits['has_modifiers'] is False

    def test_elite_limits(self):
        limits = get_plan_limits('elite')
        assert limits['max_products'] == float('inf')
        assert limits['has_modifiers'] is True

    def test_trial_limits(self):
        limits = get_plan_limits('trial')
        assert limits['max_products'] == float('inf')
        assert limits['has_modifiers'] is True

    def test_unknown_plan_defaults_to_emprendedor(self):
        limits = get_plan_limits('nonexistent')
        assert limits['name'] == 'Emprendedor'


class TestCheckProductLimit:

    def test_within_limit(self, db, sample_restaurant):
        allowed, msg = check_product_limit(sample_restaurant)
        assert allowed is True
        assert 'disponible' in msg

    def test_exceeded_limit(self, db, sample_restaurant):
        _create_products(db, sample_restaurant, count=25, is_active=True)
        allowed, msg = check_product_limit(sample_restaurant)
        assert allowed is False
        assert 'límite' in msg

    def test_exact_limit(self, db, sample_restaurant):
        _create_products(db, sample_restaurant, count=24, is_active=True)
        allowed, msg = check_product_limit(sample_restaurant)
        assert allowed is True

    def test_inactive_products_not_counted(self, db, sample_restaurant):
        _create_products(db, sample_restaurant, count=25, is_active=False)
        allowed, msg = check_product_limit(sample_restaurant)
        assert allowed is True

    def test_expired_restaurant(self, db, expired_restaurant):
        allowed, msg = check_product_limit(expired_restaurant)
        assert allowed is False
        assert 'expirado' in msg

    def test_none_restaurant(self):
        allowed, msg = check_product_limit(None)
        assert allowed is False
        assert 'no encontrado' in msg

    def test_infinity_limit(self, db, trial_restaurant):
        allowed, msg = check_product_limit(trial_restaurant)
        assert allowed is True
        assert 'ilimitados' in msg


class TestSanitizeRestaurantLimits:

    def test_deactivates_excess_products(self, db, sample_restaurant):
        _create_products(db, sample_restaurant, count=28, is_active=True)
        sanitize_restaurant_limits(sample_restaurant)
        active_count = Product.query.filter_by(
            restaurant_id=sample_restaurant.id,
            is_active=True
        ).count()
        assert active_count == 25

    def test_does_not_affect_within_limits(self, db, sample_restaurant):
        _create_products(db, sample_restaurant, count=10, is_active=True)
        sanitize_restaurant_limits(sample_restaurant)
        active_count = Product.query.filter_by(
            restaurant_id=sample_restaurant.id,
            is_active=True
        ).count()
        assert active_count == 10

    def test_none_restaurant(self, db):
        sanitize_restaurant_limits(None)


class TestTokenWalletIntegration:

    def test_token_wallet_created_on_setup(self, db, sample_restaurant, sample_user):
        from app.utils.subscription import initialize_or_reset_token_wallet
        wallet = initialize_or_reset_token_wallet(sample_user)
        assert wallet is not None
        assert wallet.user_id == sample_user.id
        assert wallet.plan_tokens >= 0

    def test_existing_wallet_not_duplicated(self, db, sample_user):
        from app.utils.subscription import initialize_or_reset_token_wallet
        wallet1 = initialize_or_reset_token_wallet(sample_user)
        wallet2 = initialize_or_reset_token_wallet(sample_user)
        assert wallet1.id == wallet2.id


# ───────────── Helpers ─────────────

def _make_restaurant(days_until_expiry):
    from app.models import Restaurant, db
    r = Restaurant(
        name=f'Exp Test {days_until_expiry}d',
        slug=f'exp-test-{days_until_expiry}d',
        whatsapp_phone='+573000000000',
        plan_type='emprendedor',
        is_active=True,
        is_open=True,
        subscription_expires_at=(
            datetime.now(timezone.utc) + timedelta(days=days_until_expiry)
        ),
    )
    db.session.add(r)
    db.session.commit()
    return r


def _create_products(db, restaurant, count, is_active=True, category_id=None):
    if category_id is None:
        from app.models import Category
        cat = Category(
            restaurant_id=restaurant.id,
            name='Test Category',
            sort_order=1,
            is_active=True,
        )
        db.session.add(cat)
        db.session.flush()
        category_id = cat.id

    for i in range(count):
        p = Product(
            restaurant_id=restaurant.id,
            category_id=category_id,
            name=f'Product {i + 1}',
            price=1000,
            is_active=is_active,
        )
        db.session.add(p)
    db.session.commit()

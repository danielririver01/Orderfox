import pytest
import os
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'
os.environ['JWT_SECRET_KEY'] = 'test-secret-key-for-testing-only'

from app import create_app
from app.models import db as _db
from app.models import (
    Restaurant, User, Order, OrderItem, Category, Product,
    Modifier, Table, TrialHistory, AITokenWallet, AITokenTransaction,
    DiscountCoupon
)


@pytest.fixture(scope='session')
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'MAIL_SUPPRESS_SEND': True,
    })
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.close()
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.session.close()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


# ───────────── Factory Fixtures ─────────────

@pytest.fixture
def sample_restaurant(db):
    r = Restaurant(
        name='Test Restaurant',
        slug='test-restaurant',
        whatsapp_phone='+573001234567',
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
def sample_user(db, sample_restaurant):
    u = User(
        restaurant_id=sample_restaurant.id,
        username='admin',
        email='admin@test.com',
        password=generate_password_hash('TestPass123'),
        clerk_id='clerk_test_123',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def sample_category(db, sample_restaurant):
    c = Category(
        restaurant_id=sample_restaurant.id,
        name='Bebidas',
        sort_order=1,
        is_active=True,
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def sample_product(db, sample_restaurant, sample_category):
    p = Product(
        restaurant_id=sample_restaurant.id,
        category_id=sample_category.id,
        name='Coca Cola',
        price=5000,
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def sample_order(db, sample_restaurant):
    o = Order(
        restaurant_id=sample_restaurant.id,
        order_number='ORD-001',
        customer_name='Cliente Test',
        customer_phone='+573001234567',
        status='pending',
        total=15000,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(o)
    db.session.commit()
    return o


@pytest.fixture
def expired_restaurant(db):
    r = Restaurant(
        name='Expired Restaurant',
        slug='expired-restaurant',
        whatsapp_phone='+573009876543',
        plan_type='emprendedor',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) - timedelta(days=15),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def grace_period_restaurant(db):
    r = Restaurant(
        name='Grace Restaurant',
        slug='grace-restaurant',
        whatsapp_phone='+573005555555',
        plan_type='emprendedor',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) - timedelta(days=2),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def sample_coupon(db, sample_restaurant):
    c = DiscountCoupon(
        restaurant_id=sample_restaurant.id,
        percentage=20,
        status='pending',
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def expired_coupon(db, sample_restaurant):
    c = DiscountCoupon(
        restaurant_id=sample_restaurant.id,
        percentage=15,
        status='pending',
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def trial_restaurant(db):
    r = Restaurant(
        name='Trial Restaurant',
        slug='trial-restaurant',
        whatsapp_phone='+573006666666',
        plan_type='trial',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        has_used_trial=True,
    )
    db.session.add(r)
    db.session.commit()
    return r

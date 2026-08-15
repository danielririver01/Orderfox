"""
Tests del rediseño del menú digital público (v1.5):
- Campos nuevos del payload (cover_image, estimated_time, brand_color, cuisine_type)
- Fallback de portada por cuisine_type (banco curado, nunca null)
- Badges de producto (is_vegetarian, is_spicy, is_featured)
- Backward-compat del payload
- Restaurante cerrado → 200 con is_open=false (menú visible, pedidos bloqueados)
- Categorías vacías excluidas del payload
"""
import time
from datetime import datetime, timedelta, timezone

from app.models import Category, Restaurant
from app.services.public_menu_service import PublicMenuService
from app.utils.cover_bank import COVER_BANK, DEFAULT_COVER, resolve_cover


def _closed_restaurant(db):
    r = Restaurant(
        name='Closed Restaurant',
        slug='closed-restaurant',
        whatsapp_phone='+573007777777',
        plan_type='emprendedor',
        is_active=True,
        is_open=False,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.session.add(r)
    db.session.commit()
    return r


class TestMenuPayload:
    def test_menu_payload_restaurant_new_fields(self, db, sample_restaurant, sample_category, sample_product):
        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        rest = data['restaurant']
        assert rest['cover_image'] and isinstance(rest['cover_image'], str)
        assert 'estimated_time' in rest
        assert 'brand_color' in rest
        assert rest['cuisine_type'] == 'general'

    def test_menu_payload_backward_compat(self, db, sample_restaurant, sample_category, sample_product):
        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        rest = data['restaurant']
        assert rest['id'] == sample_restaurant.id
        assert rest['name'] == sample_restaurant.name
        assert rest['slug'] == sample_restaurant.slug
        assert rest['whatsapp_phone'] == sample_restaurant.whatsapp_phone
        assert 'is_open' in rest
        assert 'ordering_disabled' in rest

        cat = data['categories'][0]
        assert cat['id'] == sample_category.id
        assert cat['name'] == sample_category.name
        assert 'image_url' in cat
        assert cat['product_count'] == 1
        product = cat['products'][0]
        assert product['id'] == sample_product.id
        assert product['name'] == sample_product.name
        assert product['price'] == 5000
        assert 'image_url' in product
        assert 'modifiers' in product

    def test_menu_product_badges_default_false(self, db, sample_restaurant, sample_category, sample_product):
        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        product = data['categories'][0]['products'][0]
        assert product['is_vegetarian'] is False
        assert product['is_spicy'] is False
        assert product['is_featured'] is False

    def test_menu_product_badges_set(self, db, sample_restaurant, sample_category, sample_product):
        sample_product.is_vegetarian = True
        sample_product.is_spicy = True
        sample_product.is_featured = True
        db.session.commit()
        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        product = data['categories'][0]['products'][0]
        assert product['is_vegetarian'] is True
        assert product['is_spicy'] is True
        assert product['is_featured'] is True

    def test_menu_excludes_empty_categories(self, db, sample_restaurant, sample_category, sample_product):
        empty = Category(restaurant_id=sample_restaurant.id, name='Vacia', sort_order=99, is_active=True)
        db.session.add(empty)
        db.session.commit()
        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        names = [c['name'] for c in data['categories']]
        assert 'Vacia' not in names
        assert len(data['categories']) == 1


class TestCoverBank:
    def test_fallback_by_cuisine(self, db, sample_restaurant):
        sample_restaurant.cuisine_type = 'italiana'
        db.session.commit()
        assert resolve_cover(sample_restaurant) == COVER_BANK['italiana']

    def test_uses_own_image(self, db, sample_restaurant):
        sample_restaurant.cuisine_type = 'italiana'
        sample_restaurant.cover_image = 'https://example.com/mi-portada.jpg'
        db.session.commit()
        assert resolve_cover(sample_restaurant) == 'https://example.com/mi-portada.jpg'

    def test_unknown_cuisine_falls_to_general(self, db, sample_restaurant):
        sample_restaurant.cuisine_type = 'marciana'
        db.session.commit()
        assert resolve_cover(sample_restaurant) == DEFAULT_COVER

    def test_never_returns_none(self, db, sample_restaurant):
        in_memory = Restaurant(
            name='Sin Tipo', slug='sin-tipo', whatsapp_phone='+573008888888',
            plan_type='emprendedor', is_active=True,
            subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert in_memory.cuisine_type is None
        assert resolve_cover(in_memory) == DEFAULT_COVER


class TestMenuApi:
    def test_api_menu_200_structure(self, client, sample_restaurant, sample_category, sample_product):
        res = client.get('/api/public/menu/test-restaurant')
        assert res.status_code == 200
        body = res.get_json()
        assert body['success'] is True
        rest = body['data']['restaurant']
        assert rest['cuisine_type'] == 'general'
        assert rest['cover_image']
        assert rest['estimated_time'] is None
        assert rest['brand_color'] is None

    def test_api_menu_closed_returns_200_with_is_open_false(self, client, db, sample_restaurant, sample_category, sample_product):
        sample_restaurant.is_open = False
        db.session.commit()
        res = client.get('/api/public/menu/test-restaurant')
        assert res.status_code == 200
        body = res.get_json()
        assert body['success'] is True
        assert body['data']['restaurant']['is_open'] is False
        assert len(body['data']['categories']) >= 1

    def test_api_category_includes_badges(self, client, sample_restaurant, sample_category, sample_product):
        res = client.get(f'/api/public/menu/test-restaurant/categoria/{sample_category.id}')
        assert res.status_code == 200
        body = res.get_json()
        product = body['data']['products'][0]
        assert 'is_vegetarian' in product
        assert 'is_spicy' in product
        assert 'is_featured' in product

    def test_api_novedades_includes_badges(self, client, sample_restaurant, sample_category, sample_product):
        res = client.get('/api/public/menu/test-restaurant/novedades')
        assert res.status_code == 200
        body = res.get_json()
        product = body['data']['products'][0]
        assert 'is_vegetarian' in product
        assert 'is_spicy' in product
        assert 'is_featured' in product


class TestOrderBlockedWhenClosed:
    def test_order_rejected_when_closed(self, client, db, sample_restaurant, sample_category, sample_product):
        sample_restaurant.is_open = False
        db.session.commit()

        with client.session_transaction() as sess:
            sess['checkout_start_time'] = time.time() - 5

        res = client.post('/menu/api/order', json={
            'restaurant_id': sample_restaurant.id,
            'cart': {sample_product.id: {'quantity': 1, 'extras': []}},
            'customer_name': 'Cliente Test',
            'customer_phone': '+573001234567',
        })
        assert res.status_code == 403
        assert 'cerrados' in res.get_json()['error']

    def test_order_ok_when_open(self, client, db, sample_restaurant, sample_category, sample_product):
        with client.session_transaction() as sess:
            sess['checkout_start_time'] = time.time() - 5

        res = client.post('/menu/api/order', json={
            'restaurant_id': sample_restaurant.id,
            'cart': {sample_product.id: {'quantity': 1, 'extras': []}},
            'customer_name': 'Cliente Test',
            'customer_phone': '+573001234567',
        })
        assert res.status_code == 200
        assert res.get_json()['success'] is True
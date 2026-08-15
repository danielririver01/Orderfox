"""
Tests de defaults de columnas del rediseño del menú público (v1.5).
"""
from app.models import Product


class TestModelDefaults:
    def test_product_badges_default_false(self, db, sample_restaurant, sample_category):
        p = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Sin badges',
            price=1000,
        )
        db.session.add(p)
        db.session.commit()
        assert p.is_vegetarian is False
        assert p.is_spicy is False
        assert p.is_featured is False

    def test_product_badges_explicit(self, db, sample_restaurant, sample_category):
        p = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Con badges',
            price=2000,
            is_vegetarian=True,
            is_spicy=False,
            is_featured=True,
        )
        db.session.add(p)
        db.session.commit()
        assert p.is_vegetarian is True
        assert p.is_featured is True

    def test_restaurant_cuisine_default_general(self, db, sample_restaurant):
        assert sample_restaurant.cuisine_type == 'general'

    def test_restaurant_new_branding_fields_nullable(self, db, sample_restaurant):
        assert sample_restaurant.cover_image is None
        assert sample_restaurant.estimated_time is None
        assert sample_restaurant.brand_color is None

    def test_restaurant_branding_fields_set(self, db, sample_restaurant):
        sample_restaurant.cover_image = 'https://example.com/cover.jpg'
        sample_restaurant.estimated_time = 25
        sample_restaurant.brand_color = '#FF7A29'
        sample_restaurant.cuisine_type = 'parrilla'
        db.session.commit()
        assert sample_restaurant.cover_image == 'https://example.com/cover.jpg'
        assert sample_restaurant.estimated_time == 25
        assert sample_restaurant.brand_color == '#FF7A29'
        assert sample_restaurant.cuisine_type == 'parrilla'
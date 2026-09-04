import json
from unittest.mock import patch, MagicMock
from app.utils import latam_photo_library
from app.services.auto_photo_service import AutoPhotoService
from app.models import Product


class TestLatamPhotoLibrary:

    def test_exact_match(self):
        url = latam_photo_library.lookup("bandeja paisa")
        assert url is not None
        assert "images.unsplash.com" in url

    def test_substring_match(self):
        url = latam_photo_library.lookup("Salchipapa Especial con Queso")
        assert url is not None
        assert url == latam_photo_library.LATAM_LIBRARY["salchipapa"]

    def test_case_and_accents_insensitivity(self):
        url1 = latam_photo_library.lookup("Buñuelo Tradicional")
        assert url1 is not None
        url2 = latam_photo_library.lookup("AJIACO SANTAFEREÑO")
        assert url2 is not None

    def test_unknown_dish(self):
        url = latam_photo_library.lookup("PlatoSuperDesconocidoXYZ123")
        assert url is None


class TestAutoPhotoServiceSwap:

    def test_swap_not_auto_image(self, db, sample_restaurant, sample_category):
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Prueba Sin Auto",
            price=10000,
            is_auto_image=False,
        )
        db.session.add(product)
        db.session.commit()

        res = AutoPhotoService.swap_suggested(product.id, sample_restaurant.id)
        assert res['success'] is False
        assert 'no tiene fotos alternativas' in res['error']

    def test_swap_empty_pool(self, db, sample_restaurant, sample_category):
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Prueba Pool Vacio",
            price=10000,
            is_auto_image=True,
            suggested_image_pool=json.dumps([]),
        )
        db.session.add(product)
        db.session.commit()

        res = AutoPhotoService.swap_suggested(product.id, sample_restaurant.id)
        assert res['success'] is True
        assert res['pool_remaining'] == 0
        assert 'No hay mas fotos alternativas' in res.get('message', '')

    def test_swap_success(self, db, sample_restaurant, sample_category):
        pool = [
            "https://images.unsplash.com/photo-2",
            "https://images.unsplash.com/photo-3"
        ]
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Hamburguesa Doble",
            price=18000,
            image_url="https://images.unsplash.com/photo-1",
            is_auto_image=True,
            suggested_image_pool=json.dumps(pool),
        )
        db.session.add(product)
        db.session.commit()

        # Primer swap
        res = AutoPhotoService.swap_suggested(product.id, sample_restaurant.id)
        assert res['success'] is True
        assert res['image_url'] == "https://images.unsplash.com/photo-2"
        assert res['pool_remaining'] == 1

        # Verificar en DB
        db.session.refresh(product)
        assert product.image_url == "https://images.unsplash.com/photo-2"
        remaining = json.loads(product.suggested_image_pool)
        assert remaining == ["https://images.unsplash.com/photo-3"]

        # Segundo swap (agotar el pool)
        res2 = AutoPhotoService.swap_suggested(product.id, sample_restaurant.id)
        assert res2['success'] is True
        assert res2['image_url'] == "https://images.unsplash.com/photo-3"
        assert res2['pool_remaining'] == 0

        db.session.refresh(product)
        assert product.suggested_image_pool is None


class TestAutoPhotoServicePipeline:

    def test_process_latam_match(self, app, db, sample_restaurant, sample_category):
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Bandeja Paisa Especial",
            price=25000,
        )
        db.session.add(product)
        db.session.commit()

        AutoPhotoService._process(product.id, product.name, sample_restaurant.id)

        db.session.refresh(product)
        assert product.image_url is not None
        assert product.image_source == 'local_library'
        assert product.is_auto_image is True

    def test_process_skips_if_has_image(self, app, db, sample_restaurant, sample_category):
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Bandeja Paisa",
            price=25000,
            image_url="https://misitio.com/foto_real.jpg",
            image_source="user_upload",
            is_auto_image=False,
        )
        db.session.add(product)
        db.session.commit()

        AutoPhotoService._process(product.id, product.name, sample_restaurant.id)

        db.session.refresh(product)
        assert product.image_url == "https://misitio.com/foto_real.jpg"
        assert product.is_auto_image is False

    def test_enqueue_disabled(self, app):
        with patch.object(app, 'config', {'AUTOPHOTO_ENABLED': False}):
            with patch('threading.Thread.start') as mock_start:
                AutoPhotoService.enqueue(app, 999, "Producto", 1)
                mock_start.assert_not_called()


class TestAutoPhotoUniqueness:
    """Tests for the Unsplash uniqueness filter (unsplash_source_url)."""

    def test_get_used_urls_returns_source_urls(self, db, sample_restaurant, sample_category):
        """_get_used_urls() should return only the unsplash_source_url values."""
        p1 = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Prod A",
            price=10000,
            unsplash_source_url="https://images.unsplash.com/photo-111",
        )
        p2 = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Prod B",
            price=10000,
            unsplash_source_url="https://images.unsplash.com/photo-222",
        )
        p3 = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Prod C",
            price=10000,
            # sin unsplash_source_url (upload manual)
        )
        db.session.add_all([p1, p2, p3])
        db.session.commit()

        used = AutoPhotoService._get_used_urls(sample_restaurant.id)
        assert used == {
            "https://images.unsplash.com/photo-111",
            "https://images.unsplash.com/photo-222",
        }

    def test_get_used_urls_ignores_other_restaurants(self, db, sample_restaurant, sample_category):
        """Unicidad es por restaurante, no global."""
        from app.models import Restaurant

        other_restaurant = Restaurant(
            name="Otro",
            slug="otro-rest",
            whatsapp_phone="+573009999999",
            plan_type="emprendedor",
            is_active=True,
            is_open=True,
        )
        db.session.add(other_restaurant)
        db.session.flush()

        p_other = Product(
            restaurant_id=other_restaurant.id,
            category_id=sample_category.id,
            name="Prod Otro",
            price=10000,
            unsplash_source_url="https://images.unsplash.com/photo-999",
        )
        p_mine = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Prod Mio",
            price=10000,
            unsplash_source_url="https://images.unsplash.com/photo-111",
        )
        db.session.add_all([p_other, p_mine])
        db.session.commit()

        used = AutoPhotoService._get_used_urls(sample_restaurant.id)
        assert used == {"https://images.unsplash.com/photo-111"}
        assert "https://images.unsplash.com/photo-999" not in used

    def test_assign_stores_unsplash_source_url(self, app, db, sample_restaurant, sample_category):
        """_assign() should store unsplash_source_url when provided."""
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Test Assign",
            price=10000,
        )
        db.session.add(product)
        db.session.commit()

        AutoPhotoService._assign(
            product,
            "https://res.cloudinary.com/test/image.jpg",
            "unsplash",
            ["https://res.cloudinary.com/test/alt1.jpg"],
            unsplash_source_url="https://images.unsplash.com/photo-ABC",
        )

        db.session.refresh(product)
        assert product.unsplash_source_url == "https://images.unsplash.com/photo-ABC"
        assert product.image_source == "unsplash"

    def test_assign_no_source_url_when_not_unsplash(self, app, db, sample_restaurant, sample_category):
        """_assign() should NOT set unsplash_source_url for local_library."""
        product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Test Local",
            price=10000,
        )
        db.session.add(product)
        db.session.commit()

        AutoPhotoService._assign(
            product,
            "https://images.unsplash.com/photo-LOCAL",
            "local_library",
            [],
        )

        db.session.refresh(product)
        assert product.unsplash_source_url is None
        assert product.image_source == "local_library"

    def test_process_filters_used_urls(self, app, db, sample_restaurant, sample_category):
        """_process() should skip Unsplash photos already used in the restaurant."""
        # Create a product that already uses photo-111
        existing = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Existing Prod",
            price=10000,
            image_url="https://res.cloudinary.com/test/photo-111.jpg",
            image_source="unsplash",
            is_auto_image=True,
            unsplash_source_url="https://images.unsplash.com/photo-111",
        )
        db.session.add(existing)
        db.session.commit()

        # New product that will hit Unsplash (not LATAM — avoid names in the library)
        new_product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Wagyu Steak Premium",
            price=15000,
        )
        db.session.add(new_product)
        db.session.commit()

        # Mock Unsplash to return photo-111 (already used) and photo-222
        fake_pool = [
            "https://images.unsplash.com/photo-111?q=80&w=800",
            "https://images.unsplash.com/photo-222?q=80&w=800",
        ]
        with patch.object(AutoPhotoService, '_unsplash_search', return_value=fake_pool), \
             patch.object(AutoPhotoService, '_upload_to_cloudinary', side_effect=lambda u: u), \
             patch.object(AutoPhotoService, '_extract_keyword', return_value="pizza food"):

            AutoPhotoService._process(new_product.id, new_product.name, sample_restaurant.id)

        db.session.refresh(new_product)
        # Should have assigned photo-222 (not photo-111 which was already used)
        assert new_product.unsplash_source_url == "https://images.unsplash.com/photo-222"
        assert new_product.image_source == "unsplash"

    def test_process_falls_back_to_category(self, app, db, sample_restaurant, sample_category):
        """When keyword search is exhausted, should try category keyword."""
        # Mark all photos from keyword search as used
        for i in range(5):
            p = Product(
                restaurant_id=sample_restaurant.id,
                category_id=sample_category.id,
                name=f"Prod {i}",
                price=10000,
                image_url=f"https://res.cloudinary.com/test/photo-{i}.jpg",
                image_source="unsplash",
                is_auto_image=True,
                unsplash_source_url=f"https://images.unsplash.com/photo-{i}",
            )
            db.session.add(p)
        db.session.commit()

        # Use a name that does NOT match the LATAM library
        new_product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Smoked Brisket BBQ",
            price=12000,
        )
        db.session.add(new_product)
        db.session.commit()

        # Keyword search returns only used photos, category search returns new ones
        keyword_pool = [f"https://images.unsplash.com/photo-{i}?q=80&w=800" for i in range(5)]
        category_pool = [
            "https://images.unsplash.com/photo-CAT1?q=80&w=800",
            "https://images.unsplash.com/photo-CAT2?q=80&w=800",
        ]

        with patch.object(AutoPhotoService, '_unsplash_search', side_effect=[keyword_pool, category_pool]), \
             patch.object(AutoPhotoService, '_upload_to_cloudinary', side_effect=lambda u: u), \
             patch.object(AutoPhotoService, '_extract_keyword', return_value="smoked brisket"), \
             patch.object(AutoPhotoService, '_extract_category', return_value="bbq food"):

            AutoPhotoService._process(new_product.id, new_product.name, sample_restaurant.id)

        db.session.refresh(new_product)
        assert new_product.unsplash_source_url == "https://images.unsplash.com/photo-CAT1"
        assert new_product.image_source == "unsplash"

    def test_process_fallback_silent_when_fully_exhausted(self, app, db, sample_restaurant, sample_category):
        """When both keyword and category searches are exhausted, no image assigned."""
        # Fill all possible photos
        for i in range(10):
            p = Product(
                restaurant_id=sample_restaurant.id,
                category_id=sample_category.id,
                name=f"Prod {i}",
                price=10000,
                image_url=f"https://res.cloudinary.com/test/photo-{i}.jpg",
                image_source="unsplash",
                is_auto_image=True,
                unsplash_source_url=f"https://images.unsplash.com/photo-{i}",
            )
            db.session.add(p)
        db.session.commit()

        # Use a name that does NOT match the LATAM library
        new_product = Product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name="Truffle Risotto Deluxe",
            price=18000,
        )
        db.session.add(new_product)
        db.session.commit()

        # Both searches return only used photos
        all_used = [f"https://images.unsplash.com/photo-{i}?q=80&w=800" for i in range(10)]

        with patch.object(AutoPhotoService, '_unsplash_search', return_value=all_used), \
             patch.object(AutoPhotoService, '_extract_keyword', return_value="truffle risotto"), \
             patch.object(AutoPhotoService, '_extract_category', return_value="italian food"):

            AutoPhotoService._process(new_product.id, new_product.name, sample_restaurant.id)

        db.session.refresh(new_product)
        assert new_product.image_url is None
        assert new_product.image_source is None

    def test_extract_category_broadens_keyword(self):
        """_extract_category() should produce a generic category from product name."""
        cat = AutoPhotoService._extract_category("Hamburguesa Especial Doble Queso")
        assert "food" in cat
        # Should not be the exact product name
        assert cat != "Hamburguesa Especial Doble Queso"

    def test_extract_category_fallback(self):
        """_extract_category() with a single-word name should still return something useful."""
        cat = AutoPhotoService._extract_category("X")
        assert "food" in cat or "plate" in cat

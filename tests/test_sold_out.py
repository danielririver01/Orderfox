"""
Tests del estado "Agotado" (is_sold_out):

- El dueño puede marcar/desmarcar "hoy no hay" al crear o editar un producto.
- Un producto agotado NO desaparece del menú público: sigue apareciendo,
  con is_sold_out=true, para que el cliente lo vea tachado y entienda por qué.
- is_sold_out no afecta is_active ni el límite de productos.
- update_product con is_sold_out=None no toca el campo.
"""
from app.models import Product
from app.services.product_service import ProductService
from app.services.public_menu_service import PublicMenuService


class TestSoldOutService:
    def test_create_product_sold_out(self, db, sample_restaurant, sample_category):
        product, error = ProductService.create_product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Bandeja paisa',
            price=28000,
            is_sold_out=True,
        )
        assert error is None
        assert product.is_sold_out is True
        # Agotado no lo saca del menú: sigue activo y visible.
        assert product.is_active is True

    def test_create_product_default_not_sold_out(self, db, sample_restaurant, sample_category):
        product, error = ProductService.create_product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Sancocho',
            price=15000,
        )
        assert error is None
        assert product.is_sold_out is False

    def test_update_product_toggle_sold_out(self, db, sample_restaurant, sample_category):
        product, error = ProductService.create_product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Ajiaco',
            price=22000,
        )
        assert error is None
        assert product.is_sold_out is False

        product, error = ProductService.update_product(product, is_sold_out=True)
        assert error is None
        assert product.is_sold_out is True

        product, error = ProductService.update_product(product, is_sold_out=False)
        assert error is None
        assert product.is_sold_out is False

    def test_update_product_none_does_not_touch_sold_out(self, db, sample_restaurant, sample_category):
        product, error = ProductService.create_product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Limonada',
            price=6000,
            is_sold_out=True,
        )
        assert error is None

        # Editar el nombre sin pasar is_sold_out: el estado se conserva.
        product, error = ProductService.update_product(product, name='Limonada natural')
        assert error is None
        assert product.name == 'Limonada natural'
        assert product.is_sold_out is True


class TestSoldOutPublicMenu:
    def test_sold_out_product_stays_in_menu_with_flag(
            self, db, sample_restaurant, sample_category, sample_product):
        sample_product.is_sold_out = True
        db.session.commit()

        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        productos = [
            p for cat in data['categories'] for p in cat['products']
        ]
        agotado = next(p for p in productos if p['id'] == sample_product.id)
        # Sigue en el menú (no desaparece) y viaja la bandera para tacharlo.
        assert agotado['is_sold_out'] is True

    def test_active_product_has_sold_out_false(
            self, db, sample_restaurant, sample_category, sample_product):
        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        productos = [
            p for cat in data['categories'] for p in cat['products']
        ]
        normal = next(p for p in productos if p['id'] == sample_product.id)
        assert normal['is_sold_out'] is False

    def test_inactive_product_still_hidden_even_if_not_sold_out(
            self, db, sample_restaurant, sample_category, sample_product):
        """is_active=False sigue ocultando el producto del menú público."""
        sample_product.is_active = False
        db.session.commit()

        data = PublicMenuService.get_menu_api_data(sample_restaurant)
        productos = [
            p for cat in data['categories'] for p in cat['products']
        ]
        assert all(p['id'] != sample_product.id for p in productos)

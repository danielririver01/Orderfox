import io
from unittest.mock import patch, Mock

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app.models import Product, Category
from app.services.product_service import ProductService
from app.services.category_service import CategoryService
from app.utils.image_handler import save_image, allowed_file, delete_image


def _jpeg_file(filename='foto.jpg', size=(80, 80), color='red'):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, format='JPEG')
    buf.seek(0)
    return FileStorage(stream=buf, filename=filename)


def _garbage_file(filename='foto.jpg'):
    return FileStorage(stream=io.BytesIO(b'\x00\x01\x02 not an image'), filename=filename)


class TestAllowedFile:
    def test_allowed_extensions(self):
        assert allowed_file('foto.jpg')
        assert allowed_file('foto.JPEG')
        assert allowed_file('foto.png')
        assert allowed_file('foto.webp')

    def test_rejects_unsupported(self):
        assert not allowed_file('foto.heic')
        assert not allowed_file('foto.heif')
        assert not allowed_file('foto.txt')
        assert not allowed_file('foto')
        assert not allowed_file('')


class TestSaveImage:
    def test_uploads_and_returns_url(self, app):
        with app.app_context():
            app.config.update({
                'CLOUDINARY_CLOUD_NAME': 'test',
                'CLOUDINARY_API_KEY': 'key',
                'CLOUDINARY_API_SECRET': 'secret',
            })
            with patch('cloudinary.uploader.upload', return_value={
                    'secure_url': 'https://res.cloudinary.com/test/image/upload/velzia/products/x.jpg'}):
                url = save_image(_jpeg_file(), 'products')
        assert url == 'https://res.cloudinary.com/test/image/upload/velzia/products/x.jpg'

    def test_returns_none_for_unsupported_format(self, app):
        with app.app_context():
            assert save_image(_jpeg_file(filename='foto.heic'), 'products') is None

    def test_returns_none_for_corrupt_image(self, app):
        with app.app_context():
            with patch('cloudinary.uploader.upload', return_value={'secure_url': 'x'}):
                assert save_image(_garbage_file(), 'products') is None

    def test_decompression_bomb_guard_disabled(self):
        buf = io.BytesIO()
        Image.new('RGB', (2000, 2000), 'blue').save(buf, format='JPEG')
        buf.seek(0)
        assert Image.MAX_IMAGE_PIXELS is None
        with patch('PIL.Image.MAX_IMAGE_PIXELS', 100):
            with pytest.raises(Image.DecompressionBombError):
                Image.open(buf)
        buf.seek(0)
        img = Image.open(buf)
        assert img.size == (2000, 2000)
        img.close()


class TestProductServiceImage:
    def test_create_product_with_image(self, db, sample_restaurant, sample_category):
        with patch('app.services.product_service.save_image',
                   return_value='https://cdn/velzia/products/p.jpg') as mock_save:
            product, error = ProductService.create_product(
                restaurant_id=sample_restaurant.id,
                category_id=sample_category.id,
                name='Hamburguesa',
                price=15000,
                image_file=_jpeg_file(),
            )
        assert error is None
        assert product.image_url == 'https://cdn/velzia/products/p.jpg'
        mock_save.assert_called_once()
        db.session.expire_all()

    def test_create_product_surfaces_image_error(self, db, sample_restaurant,
                                                 sample_category):
        with patch('app.services.product_service.save_image', return_value=None):
            product, error = ProductService.create_product(
                restaurant_id=sample_restaurant.id,
                category_id=sample_category.id,
                name='Sin Foto',
                price=10000,
                image_file=_jpeg_file(),
            )
        assert product is None
        assert 'No se pudo subir la imagen' in error
        assert Product.query.count() == 0

    def test_create_product_without_image(self, db, sample_restaurant,
                                          sample_category):
        product, error = ProductService.create_product(
            restaurant_id=sample_restaurant.id,
            category_id=sample_category.id,
            name='Sin Foto',
            price=10000,
        )
        assert error is None
        assert product.image_url is None

    def test_update_product_success_deletes_old_after(self, db, sample_product):
        sample_product.image_url = 'https://cdn/velzia/products/old.jpg'
        db.session.commit()
        with patch('app.services.product_service.save_image',
                   return_value='https://cdn/velzia/products/new.jpg') as mock_save, \
                patch('app.services.product_service.delete_image') as mock_delete:
            product, error = ProductService.update_product(
                product=sample_product,
                name='Nuevo',
                image_file=_jpeg_file(),
            )
        assert error is None
        assert product.image_url == 'https://cdn/velzia/products/new.jpg'
        mock_delete.assert_called_once_with('https://cdn/velzia/products/old.jpg')

    def test_update_product_error_keeps_old_image(self, db, sample_product):
        sample_product.image_url = 'https://cdn/velzia/products/old.jpg'
        db.session.commit()
        with patch('app.services.product_service.save_image', return_value=None) as mock_save, \
                patch('app.services.product_service.delete_image') as mock_delete:
            product, error = ProductService.update_product(
                product=sample_product,
                name='Nuevo',
                image_file=_jpeg_file(),
            )
        assert product is None
        assert 'No se pudo subir la imagen' in error
        mock_delete.assert_not_called()
        db.session.rollback()
        db.session.expire_all()
        persisted = Product.query.get(sample_product.id)
        assert persisted.image_url == 'https://cdn/velzia/products/old.jpg'

    def test_update_product_delete_flag(self, db, sample_product):
        sample_product.image_url = 'https://cdn/velzia/products/old.jpg'
        db.session.commit()
        with patch('app.services.product_service.delete_image') as mock_delete:
            product, error = ProductService.update_product(
                product=sample_product,
                delete_image_flag=True,
            )
        assert error is None
        assert product.image_url is None
        mock_delete.assert_called_once_with('https://cdn/velzia/products/old.jpg')


class TestCategoryServiceImage:
    def test_create_category_surfaces_image_error(self, db, sample_restaurant):
        with patch('app.services.category_service.save_image', return_value=None):
            category, error = CategoryService.create_category(
                restaurant_id=sample_restaurant.id,
                name='Postres',
                image_file=_jpeg_file(),
            )
        assert category is None
        assert 'No se pudo subir la imagen' in error
        assert Category.query.count() == 0

    def test_create_category_with_image(self, db, sample_restaurant):
        with patch('app.services.category_service.save_image',
                   return_value='https://cdn/velzia/categories/c.jpg'):
            category, error = CategoryService.create_category(
                restaurant_id=sample_restaurant.id,
                name='Postres',
                image_file=_jpeg_file(),
            )
        assert error is None
        assert category.image_url == 'https://cdn/velzia/categories/c.jpg'

    def test_update_category_error_keeps_old_image(self, db, sample_category):
        sample_category.image_url = 'https://cdn/velzia/categories/old.jpg'
        db.session.commit()
        with patch('app.services.category_service.save_image', return_value=None), \
                patch('app.services.category_service.delete_image') as mock_delete:
            category, error = CategoryService.update_category(
                category=sample_category,
                name='Renombrada',
                image_file=_jpeg_file(),
            )
        assert category is None
        assert 'No se pudo subir la imagen' in error
        mock_delete.assert_not_called()
        db.session.rollback()
        db.session.expire_all()
        persisted = Category.query.get(sample_category.id)
        assert persisted.image_url == 'https://cdn/velzia/categories/old.jpg'

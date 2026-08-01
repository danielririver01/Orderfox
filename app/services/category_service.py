from app.models import db, Category, Product
from app.utils.image_handler import save_image, delete_image


class CategoryService:
    """Business logic for Category operations.
    Shared by web routes (categories_bp) and API routes (api_categories_bp).
    """

    @staticmethod
    def get_categories(restaurant_id):
        return Category.query.filter_by(
            restaurant_id=restaurant_id
        ).order_by(Category.sort_order).all()

    @staticmethod
    def get_active_categories(restaurant_id):
        """Return active categories for a restaurant (for product forms)."""
        return Category.query.filter_by(
            restaurant_id=restaurant_id, is_active=True
        ).order_by(Category.sort_order).all()

    @staticmethod
    def get_category(restaurant_id, category_id):
        return Category.query.filter_by(
            id=category_id, restaurant_id=restaurant_id
        ).first()

    @staticmethod
    def create_category(restaurant_id, name, description='', is_active=True, image_file=None):
        if not name or not name.strip():
            return None, 'Nombre es requerido'

        clean_name = name.strip()
        duplicate = Category.query.filter_by(
            restaurant_id=restaurant_id
        ).filter(db.func.lower(Category.name) == clean_name.lower()).first()
        if duplicate:
            return None, 'Ya existe una categoría con ese nombre'

        max_order = db.session.query(db.func.max(Category.sort_order)).filter_by(
            restaurant_id=restaurant_id
        ).scalar() or 0

        category = Category(
            restaurant_id=restaurant_id,
            name=name.strip(),
            description=description,
            is_active=is_active,
            sort_order=max_order + 1
        )

        if image_file and getattr(image_file, 'filename', ''):
            image_url = save_image(image_file, 'categories')
            if image_url:
                category.image_url = image_url
            else:
                return None, ('No se pudo subir la imagen. '
                              'Usa una imagen JPG, PNG o WebP de menos de 10MB.')

        db.session.add(category)
        db.session.commit()
        return category, None

    @staticmethod
    def update_category(category, name=None, description=None, is_active=None,
                        image_file=None, delete_image_flag=False):
        if name is not None:
            new_name = name.strip() if name else name
            if new_name and new_name.lower() != category.name.lower():
                duplicate = Category.query.filter_by(
                    restaurant_id=category.restaurant_id
                ).filter(db.func.lower(Category.name) == new_name.lower()).first()
                if duplicate and duplicate.id != category.id:
                    return None, 'Ya existe una categoría con ese nombre'
            category.name = new_name
        if description is not None:
            category.description = description
        if is_active is not None:
            category.is_active = is_active

        if image_file and getattr(image_file, 'filename', ''):
            image_url = save_image(image_file, 'categories')
            if image_url:
                if category.image_url:
                    delete_image(category.image_url)
                category.image_url = image_url
            else:
                return None, ('No se pudo subir la imagen. '
                              'Usa una imagen JPG, PNG o WebP de menos de 10MB.')
        elif delete_image_flag:
            if category.image_url:
                delete_image(category.image_url)
            category.image_url = None

        db.session.commit()
        return category, None

    @staticmethod
    def delete_category(category):
        """Returns (True, None) on success, (False, error_message) if has products."""
        product_count = Product.query.filter_by(
            category_id=category.id,
            restaurant_id=category.restaurant_id
        ).count()

        if product_count > 0:
            return False, f'No puedes eliminar esta categoría porque tiene {product_count} producto(s) asociado(s).'

        if category.image_url:
            delete_image(category.image_url)

        db.session.delete(category)
        db.session.commit()
        return True, None

    @staticmethod
    def toggle_category(category, desired_state=None):
        if desired_state is None:
            desired_state = not category.is_active
        category.is_active = desired_state
        db.session.commit()

    @staticmethod
    def reorder_category(category, sort_order):
        if sort_order is None:
            return False, 'sort_order requerido'
        category.sort_order = sort_order
        db.session.commit()
        return True, None

    @staticmethod
    def get_product_count(restaurant_id, category_id):
        return Product.query.filter_by(
            category_id=category_id, restaurant_id=restaurant_id
        ).count()

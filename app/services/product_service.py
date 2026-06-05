from app.models import db, Product, Modifier, Category, Restaurant
from app.utils.subscription import check_product_limit, check_feature_access
from app.utils.image_handler import save_image, delete_image


class ProductService:
    """Business logic for Product + Modifier operations.
    Shared by web routes (products_bp) and API routes (api_products_bp).
    """

    # ── Internal helpers ──────────────────────────────────

    @staticmethod
    def _get_restaurant(restaurant_id):
        """Look up Restaurant by ID for limit/feature checks."""
        return Restaurant.query.get(restaurant_id)

    # ── Product CRUD ─────────────────────────────────────

    @staticmethod
    def get_products_for_restaurant(restaurant_id, category_id=None,
                                     active_only=False, page=1, per_page=None):
        """
        Return (products_list, total_count).
        Supports filtering by category, active_only, and pagination.
        Ordered by category_id, name.
        When per_page is None, returns ALL products (no pagination).
        """
        query = Product.query.filter_by(restaurant_id=restaurant_id)

        if category_id:
            query = query.filter_by(category_id=category_id)
        if active_only:
            query = query.filter_by(is_active=True)

        query = query.order_by(Product.category_id, Product.name)

        total = query.count()

        if per_page is not None:
            products = query.offset((page - 1) * per_page).limit(per_page).all()
        else:
            products = query.all()

        return products, total

    @staticmethod
    def get_product(restaurant_id, product_id):
        """Return Product or None."""
        return Product.query.filter_by(
            id=product_id, restaurant_id=restaurant_id
        ).first()

    @staticmethod
    def create_product(restaurant_id, category_id, name, price,
                       description='', is_active=True, image_file=None):
        """
        Create a new product.

        Returns (Product, None) on success or (None, error_message) on failure.

        Validates:
        - category belongs to restaurant
        - product limit (if is_active)
        - image upload (optional)
        """
        # Validate category
        category = Category.query.filter_by(
            id=category_id, restaurant_id=restaurant_id
        ).first()
        if not category:
            return None, 'Categoría inválida'

        # Validate product limit when activating
        if is_active:
            restaurant = ProductService._get_restaurant(restaurant_id)
            if restaurant:
                allowed, message = check_product_limit(restaurant)
                if not allowed:
                    return None, message

        product = Product(
            restaurant_id=restaurant_id,
            category_id=category_id,
            name=name,
            description=description,
            price=price,
            is_active=is_active,
        )

        if image_file:
            image_url = save_image(image_file, 'products')
            if image_url:
                product.image_url = image_url

        db.session.add(product)
        db.session.commit()
        return product, None

    @staticmethod
    def update_product(product, name=None, description=None, price=None,
                       category_id=None, is_active=None,
                       image_file=None, delete_image_flag=False):
        """
        Update an existing product (partial update pattern).

        Returns (product, None) on success or (None, error_message).

        Only updates fields that are not None.
        For is_active: validates product limit when going inactive → active.
        Image: if image_file provided, replaces existing;
               if delete_image_flag=True, removes existing image.
        Category change validates the new category belongs to same restaurant.
        """
        # ── Validate category if changing ──
        if category_id is not None and category_id != product.category_id:
            category = Category.query.filter_by(
                id=category_id, restaurant_id=product.restaurant_id
            ).first()
            if not category:
                return None, 'Categoría inválida'
            product.category_id = category_id

        # ── Validate limit when activating ──
        if is_active is not None:
            if is_active and not product.is_active:
                restaurant = ProductService._get_restaurant(product.restaurant_id)
                if restaurant:
                    allowed, message = check_product_limit(restaurant)
                    if not allowed:
                        return None, message
            product.is_active = is_active

        # ── Update scalar fields ──
        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if price is not None:
            product.price = price

        # ── Image handling ──
        if image_file:
            if product.image_url:
                delete_image(product.image_url)
            image_url = save_image(image_file, 'products')
            if image_url:
                product.image_url = image_url
        elif delete_image_flag:
            if product.image_url:
                delete_image(product.image_url)
            product.image_url = None

        db.session.commit()
        return product, None

    @staticmethod
    def delete_product(product):
        """Delete a product and its associated image."""
        if product.image_url:
            delete_image(product.image_url)
        db.session.delete(product)
        db.session.commit()

    @staticmethod
    def toggle_product(product, desired_state=None):
        """
        Toggle a product's is_active state.

        Returns (product, error_message, limit_blocked).
        - limit_blocked is True when activation was rejected due to plan limit.
        - If desired_state is None, flips the current value.
        - If desired_state equals current state, no-op.
        """
        if desired_state is None:
            desired_state = not product.is_active

        # No change needed
        if product.is_active == desired_state:
            return product, None, False

        # Validate limit when activating
        if desired_state and not product.is_active:
            restaurant = ProductService._get_restaurant(product.restaurant_id)
            if restaurant:
                allowed, message = check_product_limit(restaurant)
                if not allowed:
                    return product, message, True

        # Apply change
        product.is_active = desired_state
        db.session.commit()
        return product, None, False

    @staticmethod
    def get_product_status(product):
        """Return a dict with id and is_active for JSON serialization."""
        return {'id': product.id, 'is_active': product.is_active}

    # ── Scoped helpers ───────────────────────────────────

    @staticmethod
    def get_active_count(restaurant_id):
        """Return count of active products for a restaurant."""
        return Product.query.filter_by(
            restaurant_id=restaurant_id, is_active=True
        ).count()

    @staticmethod
    def get_modifier_count(restaurant_id, product_id):
        """Return total count of modifiers for a product."""
        return Modifier.query.filter_by(
            product_id=product_id, restaurant_id=restaurant_id
        ).count()

    # ── Modifier CRUD ────────────────────────────────────

    @staticmethod
    def get_modifier(restaurant_id, modifier_id):
        """Return a Modifier by ID, scoped to restaurant."""
        return Modifier.query.filter_by(
            id=modifier_id, restaurant_id=restaurant_id
        ).first()

    @staticmethod
    def get_modifiers_for_product(restaurant_id, product_id):
        """Return list of Modifier objects for a product."""
        return Modifier.query.filter_by(
            product_id=product_id, restaurant_id=restaurant_id
        ).all()

    @staticmethod
    def create_modifier(restaurant_id, product_id, name, extra_price=0):
        """
        Create a modifier for a product.

        Returns (modifier, None) on success or (None, error_message).
        """
        product = Product.query.filter_by(
            id=product_id, restaurant_id=restaurant_id
        ).first()
        if not product:
            return None, 'Producto no encontrado'

        if not name or not name.strip():
            return None, 'Nombre es requerido'

        modifier = Modifier(
            product_id=product_id,
            restaurant_id=restaurant_id,
            name=name.strip(),
            extra_price=extra_price or 0,
            is_active=True,
        )
        db.session.add(modifier)
        db.session.commit()
        return modifier, None

    @staticmethod
    def toggle_modifier(modifier):
        """Flip is_active. Commits."""
        modifier.is_active = not modifier.is_active
        db.session.commit()

    @staticmethod
    def delete_modifier(modifier):
        """Delete modifier. Commits."""
        db.session.delete(modifier)
        db.session.commit()

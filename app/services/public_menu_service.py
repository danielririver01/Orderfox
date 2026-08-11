"""
PublicMenuService — Business logic for public-facing menu and ordering operations.
Shared by the public order API (public_bp) and the menu JSON API (api_public_bp).

Pattern: @staticmethod methods returning (result, None) / (None, error_dict).
"""
from datetime import datetime, timedelta, timezone
from flask import current_app
from sqlalchemy.orm import selectinload
import json

from app.models import db, Category, Product, Order, OrderItem, Restaurant, Table, Modifier
from app.utils.subscription import is_subscription_active, check_feature_access


class PublicMenuService:
    """Business logic for public-facing menu and ordering operations."""

    # ── Restaurant Lookup ───────────────────────────────────

    @staticmethod
    def get_first_active_restaurant():
        """Return the first active restaurant (MVP fallback when no slug)."""
        return Restaurant.query.first()

    @staticmethod
    def get_restaurant_by_id(restaurant_id):
        """Look up a restaurant by ID."""
        return Restaurant.query.get(restaurant_id)

    @staticmethod
    def get_restaurant_by_slug(slug):
        """
        Look up a restaurant by URL slug.

        Returns:
            (restaurant, None) on success,
            (None, error_dict) if not found.
        """
        restaurant = Restaurant.query.filter_by(slug=slug).first()
        if not restaurant:
            return None, {'error_code': 'RESTAURANT_NOT_FOUND',
                          'message': 'Restaurante no encontrado'}
        return restaurant, None

    # ── Menu Data Assembly ──────────────────────────────────

    @staticmethod
    def get_menu_categories_with_products(restaurant):
        """
        Build the categories → products → modifiers hierarchy
        for the public HTML menu page.

        Returns list of Category objects with eager-loaded products
        and modifiers. Categories without active products are excluded.
        Each category gets an ``active_product_count`` attribute.
        """
        categories = Category.query.options(
            selectinload(Category.products.and_(
                Product.is_active == True,
                Product.restaurant_id == restaurant.id
            )).selectinload(Product.modifiers)
        ).filter_by(
            restaurant_id=restaurant.id,
            is_active=True
        ).order_by(Category.sort_order).all()

        # Exclude categories with no active products
        categories = [cat for cat in categories if cat.products]

        for cat in categories:
            cat.active_product_count = len(cat.products)

        return categories

    @staticmethod
    def is_ordering_enabled(restaurant):
        """
        Check whether the restaurant can accept orders.

        Returns True only if the restaurant is marked active
        AND the subscription is active (including grace period).
        """
        return bool(
            restaurant.is_active
            and is_subscription_active(restaurant, include_grace_period=True)
        )

    # ── Table Lookup ────────────────────────────────────────

    @staticmethod
    def get_restaurant_table(restaurant, table_id):
        """
        Resolve a table for the restaurant if the plan allows table QR.

        Returns:
            (table, None) — table found and allowed,
            (None, None)  — not allowed or not found (silent).
        """
        has_table_qr_access = check_feature_access(restaurant, 'has_table_qr')
        if not has_table_qr_access:
            return None, None

        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).first()
        if table and table.is_active:
            return table, None
        return None, None

    # ── Pending Order Expiry ────────────────────────────────

    @staticmethod
    def expire_old_pending_orders(restaurant_id, minutes=30):
        """
        Bulk-expire pending orders older than ``minutes`` minutes.

        Silent no-op on error (logs via current_app.logger).
        """
        try:
            expiration_limit = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            updated = Order.query.filter(
                Order.restaurant_id == restaurant_id,
                Order.status == 'pending',
                Order.created_at < expiration_limit
            ).update({Order.status: 'expired'})
            if updated:
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error expiring old pending orders for restaurant {restaurant_id}: {e}"
            )

    # ── Order Notes Construction ────────────────────────────

    @staticmethod
    def build_order_notes(customer_phone, table_name=None,
                          city=None, address=None, notes=''):
        """
        Build a formatted notes string for an order.

        Priority:
          1. If table_name is set → prefix with MESA: <name>
          2. Else if city+address → prefix with ENTREGA EN: <city> - <address>
          3. Else → prefix with Teléfono de Contacto: <phone>
        """
        if table_name:
            return (
                f"MESA: {table_name.upper()}\n"
                f"Teléfono: {customer_phone}\n---\n{notes}"
            )
        elif city and address:
            return (
                f"ENTREGA EN: {city.upper()} - {address}\n"
                f"Teléfono: {customer_phone}\n---\n{notes}"
            )
        else:
            return f"Teléfono de Contacto: {customer_phone}\n---\n{notes}"

    # ── Order Creation (from Cart) ──────────────────────────

    @staticmethod
    def create_order_from_cart(restaurant, cart, customer_name, customer_phone,
                                notes, table_id, ip_address, order_number):
        """
        Create an order and its items from a public cart payload.

        ``cart`` format: {product_id: {quantity: int, extras: [{id: int, ...}]}}

        Returns:
            (order, validated_items, total) on success,
            (None, None, error_dict) on failure.
        """
        try:
            if not cart:
                return None, None, {'error_code': 'EMPTY_CART',
                                    'message': 'El carrito está vacío.'}

            order = Order(
                restaurant_id=restaurant.id,
                order_number=order_number,
                status='pending',
                total=0,
                customer_name=customer_name,
                customer_phone=customer_phone,
                notes=notes,
                table_id=table_id,
                ip_address=ip_address,
            )
            db.session.add(order)
            db.session.flush()

            order_total = 0
            validated_items = []

            # Las claves del carrito llegan como strings (JSON) y los ids de
            # producto son enteros: normalizar para que el lookup siempre acierte.
            product_ids = []
            for raw_pid in cart.keys():
                if raw_pid is None:
                    continue
                try:
                    product_ids.append(int(raw_pid))
                except (TypeError, ValueError):
                    continue

            products = Product.query.filter(
                Product.id.in_(product_ids),
                Product.restaurant_id == restaurant.id,
                Product.is_active == True
            ).all()
            products_map = {p.id: p for p in products}

            all_modifier_ids = []
            for item in cart.values():
                for extra in item.get('extras', []):
                    mid = extra.get('id')
                    if mid:
                        all_modifier_ids.append(mid)

            modifiers_map = {}
            if all_modifier_ids:
                modifiers = Modifier.query.filter(
                    Modifier.id.in_(all_modifier_ids),
                    Modifier.is_active == True
                ).all()
                modifiers_map = {m.id: m for m in modifiers}

            for product_id, item in cart.items():
                try:
                    product_id = int(product_id)
                except (TypeError, ValueError):
                    continue
                product = products_map.get(product_id)
                if not product:
                    continue

                item_price = product.price
                extras_price = 0
                modifiers_data = []

                for extra in item.get('extras', []):
                    modifier_id = extra.get('id')
                    if not modifier_id:
                        continue
                    modifier = modifiers_map.get(modifier_id)
                    if modifier and modifier.product_id == product.id:
                        extras_price += modifier.extra_price
                        modifiers_data.append({
                            'name': modifier.name,
                            'price': modifier.extra_price
                        })

                subtotal = (item_price + extras_price) * item['quantity']
                order_total += subtotal

                order_item = OrderItem(
                    order_id=order.id,
                    restaurant_id=restaurant.id,
                    product_name=product.name,
                    product_price=item_price,
                    quantity=item['quantity'],
                    modifiers_snapshot=json.dumps(modifiers_data),
                    subtotal=subtotal
                )
                db.session.add(order_item)

                validated_items.append({
                    'name': product.name,
                    'qty': item['quantity'],
                    'extras': [m['name'] for m in modifiers_data]
                })

            if not validated_items:
                db.session.rollback()
                return None, None, {'error_code': 'EMPTY_CART',
                                    'message': 'Los productos seleccionados ya no están disponibles.'}

            order.total = order_total
            db.session.commit()

            return order, validated_items, order_total

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating order from cart: {e}")
            return None, None, {'error_code': 'ORDER_CREATION_ERROR',
                                'message': 'Error al crear el pedido. Inténtalo de nuevo.'}

    # ── API Menu Data ───────────────────────────────────────

    @staticmethod
    def get_menu_api_data(restaurant):
        """
        Build the full menu JSON payload for the API /menu/<slug> endpoint.

        Returns a dict with keys: restaurant, categories.
        Returns None if an error occurs.
        """
        try:
            categories = Category.query.options(
                selectinload(Category.products.and_(
                    Product.is_active == True,
                    Product.restaurant_id == restaurant.id
                )).selectinload(Product.modifiers)
            ).filter_by(
                restaurant_id=restaurant.id,
                is_active=True
            ).order_by(Category.sort_order).all()

            categories_data = []
            for cat in categories:
                active_products = [p for p in cat.products if p.is_active]
                active_count = len(active_products)

                products_data = []
                for p in active_products:
                    modifiers = [
                        {'id': m.id, 'name': m.name, 'extra_price': m.extra_price}
                        for m in p.modifiers if m.is_active
                    ]
                    products_data.append({
                        'id': p.id,
                        'name': p.name,
                        'description': p.description,
                        'price': p.price,
                        'image_url': p.image_url,
                        'modifiers': modifiers,
                    })

                categories_data.append({
                    'id': cat.id,
                    'name': cat.name,
                    'image_url': cat.image_url,
                    'product_count': active_count,
                    'products': products_data,
                })

            is_active_sub = (
                restaurant.is_active
                and is_subscription_active(restaurant, include_grace_period=True)
            )

            return {
                'restaurant': {
                    'id': restaurant.id,
                    'name': restaurant.name,
                    'slug': restaurant.slug,
                    'whatsapp_phone': restaurant.whatsapp_phone,
                    'is_open': restaurant.is_open,
                    'ordering_disabled': not is_active_sub,
                },
                'categories': categories_data,
            }

        except Exception as e:
            current_app.logger.error(f"Error building menu API data: {e}")
            return None

    @staticmethod
    def get_category_products_data(restaurant, category_id):
        """
        Build JSON payload for the API /menu/<slug>/categoria/<id> endpoint.

        Returns (category_dict, products_list) or (None, None) on error.
        """
        try:
            category = Category.query.options(
                selectinload(Category.products.and_(
                    Product.is_active == True,
                    Product.restaurant_id == restaurant.id
                )).selectinload(Product.modifiers)
            ).filter_by(
                id=category_id,
                restaurant_id=restaurant.id,
            ).first()
            if not category:
                return None, None

            products_data = []
            for p in category.products:
                modifiers = [
                    {'id': m.id, 'name': m.name, 'extra_price': m.extra_price}
                    for m in p.modifiers if m.is_active
                ]
                products_data.append({
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'price': p.price,
                    'image_url': p.image_url,
                    'modifiers': modifiers,
                })

            category_data = {
                'id': category.id,
                'name': category.name,
                'description': category.description,
                'image_url': category.image_url,
            }
            return category_data, products_data

        except Exception as e:
            current_app.logger.error(
                f"Error building category products data: {e}"
            )
            return None, None

    @staticmethod
    def get_novedades_data(restaurant, page=1, per_page=12):
        """
        Build paginated latest-products payload for the API.

        Returns (products_list, pagination_dict) or ([], {}) on error.
        """
        try:
            query = Product.query.options(
                selectinload(Product.category)
            ).filter_by(
                restaurant_id=restaurant.id,
                is_active=True
            ).order_by(Product.created_at.desc())

            total = query.count()
            products = query.offset((page - 1) * per_page).limit(per_page).all()

            products_data = []
            for p in products:
                products_data.append({
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'price': p.price,
                    'image_url': p.image_url,
                    'category_name': p.category.name if p.category else None,
                    'created_at': p.created_at.isoformat() if p.created_at else None,
                })

            pagination = {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 0,
            }

            return products_data, pagination

        except Exception as e:
            current_app.logger.error(f"Error building novedades data: {e}")
            return [], {}

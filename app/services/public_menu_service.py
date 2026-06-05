"""
PublicMenuService — Business logic for public-facing menu and ordering operations.
Shared by web routes (public_bp, menu_bp) and API routes (api_public_bp).

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

            for product_id, item in cart.items():
                product = Product.query.filter_by(
                    id=product_id,
                    restaurant_id=restaurant.id,
                    is_active=True
                ).first()
                if not product:
                    continue

                item_price = product.price
                extras_price = 0
                modifiers_data = []

                for extra in item.get('extras', []):
                    modifier_id = extra.get('id')
                    if not modifier_id:
                        continue
                    modifier = Modifier.query.filter_by(
                        id=modifier_id,
                        product_id=product.id,
                        is_active=True
                    ).first()
                    if modifier:
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

            order.total = order_total
            db.session.commit()

            return order, validated_items, order_total

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating order from cart: {e}")
            return None, None, {'error_code': 'ORDER_CREATION_ERROR',
                                'message': 'Error al crear el pedido. Inténtalo de nuevo.'}

    # ── Search (menu_bp) ────────────────────────────────────

    @staticmethod
    def search_products_data(restaurant):
        """
        Build a flat list of all active products with category info
        and modifier presence, for the search-products endpoint.

        Returns (products_list, error_or_None).
        """
        try:
            categories = Category.query.options(
                selectinload(Category.products.and_(Product.is_active == True))
                .selectinload(Product.modifiers)
            ).filter_by(
                restaurant_id=restaurant.id,
                is_active=True
            ).all()

            products_list = []
            for category in categories:
                for product in category.products:
                    products_list.append({
                        'id': product.id,
                        'name': product.name,
                        'description': product.description,
                        'price': product.price,
                        'category_id': category.id,
                        'category_name': category.name,
                        'has_modifiers': len(product.modifiers) > 0
                    })
            return products_list, None

        except Exception as e:
            current_app.logger.error(f"Error in search_products_data: {e}")
            return [], {'error_code': 'SEARCH_ERROR',
                        'message': 'Error al buscar productos'}

    @staticmethod
    def search_products_by_query(restaurant, query):
        """
        Search products by text query (matches name, description, category name).

        Returns (matching_products_list, error_or_None).
        """
        try:
            if not query:
                return [], None

            categories = Category.query.options(
                selectinload(Category.products.and_(Product.is_active == True))
                .selectinload(Product.modifiers)
            ).filter_by(
                restaurant_id=restaurant.id,
                is_active=True
            ).all()

            query_lower = query.lower().strip()
            matching_products = []

            for category in categories:
                for product in category.products:
                    searchable_text = (
                        f"{product.name} {product.description or ''} {category.name}"
                    ).lower()
                    if query_lower in searchable_text:
                        matching_products.append({
                            'id': product.id,
                            'name': product.name,
                            'description': product.description,
                            'price': product.price,
                            'category_id': category.id,
                            'category_name': category.name,
                            'has_modifiers': len(product.modifiers) > 0
                        })

            return matching_products, None

        except Exception as e:
            current_app.logger.error(f"Error in search_products_by_query: {e}")
            return [], {'error_code': 'SEARCH_ERROR',
                        'message': 'Error al buscar productos'}

    # ── API Menu Data ───────────────────────────────────────

    @staticmethod
    def get_menu_api_data(restaurant):
        """
        Build the full menu JSON payload for the API /menu/<slug> endpoint.

        Returns a dict with keys: restaurant, categories.
        Returns None if an error occurs.
        """
        try:
            categories = Category.query.join(Product).filter(
                Category.restaurant_id == restaurant.id,
                Category.is_active == True,
                Product.is_active == True
            ).order_by(Category.sort_order).distinct().all()

            categories_data = []
            for cat in categories:
                active_count = Product.query.filter_by(
                    category_id=cat.id,
                    restaurant_id=restaurant.id,
                    is_active=True
                ).count()

                products = Product.query.filter_by(
                    category_id=cat.id,
                    restaurant_id=restaurant.id,
                    is_active=True
                ).all()

                products_data = []
                for p in products:
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
            category = Category.query.filter_by(
                id=category_id,
                restaurant_id=restaurant.id,
            ).first()
            if not category:
                return None, None

            products = Product.query.filter_by(
                category_id=category_id,
                restaurant_id=restaurant.id,
                is_active=True
            ).all()

            products_data = []
            for p in products:
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
            query = Product.query.filter_by(
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

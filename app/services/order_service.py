from datetime import datetime, date, timezone, timedelta
from app.models import db, Order, OrderItem, Product, Table, Modifier, OrderCounter
import json


class OrderService:
    """Business logic for Order operations. Shared by web and API routes."""

    @staticmethod
    def generate_order_number(restaurant_id):
        """Atomic order number generation using a DB row lock (P5)."""
        today = date.today()

        # with_for_update() locks the row to prevent race conditions
        counter = OrderCounter.query.filter_by(
            restaurant_id=restaurant_id, date=today
        ).with_for_update().first()

        if not counter:
            counter = OrderCounter(
                restaurant_id=restaurant_id,
                date=today,
                counter=1
            )
            db.session.add(counter)
        else:
            counter.counter += 1

        db.session.flush()
        return f"ORD-{counter.counter:03d}"

    @staticmethod
    def validate_status_transition(current_status, new_status):
        valid_transitions = {
            'pending': ['confirmed', 'cancelled', 'expired'],
            'confirmed': ['delivered', 'cancelled'],
            'delivered': [],
            'cancelled': ['pending'],
            'expired': []
        }
        return new_status in valid_transitions.get(current_status, [])

    @staticmethod
    def get_order_for_restaurant(restaurant_id, order_id):
        return Order.query.filter_by(id=order_id, restaurant_id=restaurant_id).first()

    @staticmethod
    def get_active_orders_query(restaurant_id):
        """Base query for active (pending/confirmed) orders."""
        return Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status.in_(['pending', 'confirmed'])
        )

    @staticmethod
    def get_today_completed_orders_query(restaurant_id):
        """Base query for today's completed (delivered/cancelled) orders."""
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        return Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status.in_(['delivered', 'cancelled']),
            Order.updated_at >= today_start
        )

    @staticmethod
    def get_combined_orders(restaurant_id, sort_order='asc'):
        """Get active + today's completed orders for display."""
        active = OrderService.get_active_orders_query(restaurant_id)
        completed = OrderService.get_today_completed_orders_query(restaurant_id)

        if sort_order == 'desc':
            active = active.order_by(Order.created_at.desc()).all()
            completed = completed.order_by(Order.created_at.desc()).all()
        else:
            active = active.order_by(Order.created_at.asc()).all()
            completed = completed.order_by(Order.created_at.asc()).all()

        return active + completed

    @staticmethod
    def create_order(restaurant_id, order_data, ip_address=None):
        """Core order creation logic shared by all entry points."""
        order_number = OrderService.generate_order_number(restaurant_id)
        expiry_hours = order_data.get('pending_expiry_hours', 24)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        order = Order(
            restaurant_id=restaurant_id,
            order_number=order_number,
            customer_name=order_data.get('customer_name', 'Cliente'),
            customer_phone=order_data.get('customer_phone', ''),
            notes=order_data.get('notes', ''),
            total=0,
            status='pending',
            table_id=order_data.get('table_id'),
            ip_address=ip_address,
            expires_at=expires_at
        )
        db.session.add(order)
        db.session.flush()
        return order

    @staticmethod
    def add_items_to_order(order, items_data, restaurant_id):
        """Validate and add items to an order. Returns (total, validated_items)."""
        total = 0
        validated_items = []

        product_ids = [item.get('product_id') for item in items_data if item.get('product_id')]
        if not product_ids:
            return 0, []

        products = Product.query.filter(
            Product.id.in_(product_ids),
            Product.restaurant_id == restaurant_id,
            Product.is_active == True
        ).all()
        products_map = {p.id: p for p in products}

        all_modifier_ids = []
        for item in items_data:
            all_modifier_ids.extend(item.get('modifier_ids', []))

        modifiers_map = {}
        if all_modifier_ids:
            modifiers = Modifier.query.filter(
                Modifier.id.in_(all_modifier_ids),
                Modifier.is_active == True
            ).all()
            modifiers_map = {m.id: m for m in modifiers}

        for item_data in items_data:
            product_id = item_data.get('product_id')
            if not product_id:
                continue

            product = products_map.get(product_id)
            if not product:
                continue

            quantity = item_data.get('quantity', 1)
            if not isinstance(quantity, (int, float)) or quantity <= 0:
                raise ValueError(f"Cantidad inválida para el producto '{product.name}': debe ser mayor a 0")
            extras_price = 0
            modifiers_data = []

            modifier_ids = item_data.get('modifier_ids', [])
            for mid in modifier_ids:
                modifier = modifiers_map.get(mid)
                if modifier and modifier.product_id == product.id:
                    extras_price += modifier.extra_price
                    modifiers_data.append({
                        'name': modifier.name,
                        'price': modifier.extra_price
                    })

            item_price = product.price
            subtotal = (item_price + extras_price) * quantity
            total += subtotal

            order_item = OrderItem(
                order_id=order.id,
                restaurant_id=restaurant_id,
                product_name=product.name,
                product_price=item_price,
                quantity=quantity,
                modifiers_snapshot=json.dumps(modifiers_data) if modifiers_data else None,
                subtotal=subtotal
            )
            db.session.add(order_item)

            validated_items.append({
                'name': product.name,
                'qty': quantity,
                'extras': [m['name'] for m in modifiers_data]
            })

        order.total = total
        return total, validated_items

    @staticmethod
    def validate_table(restaurant_id, table_id):
        """Validate that a table belongs to a restaurant. Returns Table or None."""
        from app.models import Table
        return Table.query.filter_by(id=table_id, restaurant_id=restaurant_id).first()

    @staticmethod
    def get_active_products(restaurant_id):
        """Return all active products for a restaurant."""
        return Product.query.filter_by(restaurant_id=restaurant_id, is_active=True).all()

    @staticmethod
    def change_order_status(order, new_status):
        """
        Change an order's status and commit.

        Returns the updated order.
        """
        order.status = new_status
        db.session.commit()
        return order

    @staticmethod
    def cancel_order(order):
        """
        Cancel an order (set status to 'cancelled') and commit.

        Returns (True, None) or (False, error_message).
        Skips if already delivered/cancelled.
        """
        if order.status in ['delivered', 'cancelled']:
            return False, 'No se puede cancelar un pedido entregado o ya cancelado'
        order.status = 'cancelled'
        db.session.commit()
        return True, None

    @staticmethod
    def delete_order(order):
        """
        Delete an order permanently.

        Returns (True, None) or (False, error_message).
        Only allows deletion of cancelled orders.
        """
        if order.status != 'cancelled':
            return False, 'Solo se pueden eliminar pedidos que ya han sido cancelados'
        db.session.delete(order)
        db.session.commit()
        return True, None

    @staticmethod
    def serialize_order(order):
        """Shared JSON serialization for API responses."""
        return {
            'id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'status': order.status,
            'total': order.total,
            'notes': order.notes,
            'table_name': order.table.name if order.table else None,
            'items_count': len(order.items),
            'created_at': order.created_at.isoformat() if order.created_at else None
        }

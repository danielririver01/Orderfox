from datetime import datetime, date, timezone, timedelta
from app.models import db, Order, OrderItem, Product, Table, Modifier, OrderCounter
from app.utils.timezone import today_start_utc
import json


class PaymentValidationError(ValueError):
    """Error de negocio en el registro de un pago. El mensaje es seguro para mostrar al usuario."""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class OrderService:
    """Business logic for Order operations. Shared by web and API routes."""

    PAYMENT_METHODS = ('cash', 'nequi', 'bancolombia', 'card')
    CASH_METHODS = ('cash',)

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
            'delivered': ['cancelled'],
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
        """Base query for today's completed (delivered/cancelled) orders.

        "Hoy" se calcula en hora de Colombia (medianoche Bogotá), no en UTC.
        """
        today_start = today_start_utc()
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
    def update_order_items(order, items_data, restaurant_id, payment_method=None,
                           amount_received=None):
        """
        Reemplazar los items de un pedido (edición de venta) y recalcular el total.

        - Solo pedidos NO cancelados pueden editarse.
        - Conserva el snapshot de modificadores de cada producto que ya existía
          (los OrderItem guardan nombre/precio, no FK; se matchean por nombre).
        - Si `payment_method` viene en el request, el pago se sobreescribe con
          las reglas de `_apply_payment` contra el NUEVO total (edición de pago).
        - Si NO viene, y el pedido ya estaba pagado en efectivo, recalcula el
          cambio contra el nuevo total. Si el nuevo total supera lo recibido,
          lanza error.
        - Los items que quedan con cantidad 0 (o no enviados) se eliminan.

        Lanza ValueError (cantidad inválida) o PaymentValidationError (reglas).
        Devuelve (total, validated_items) tras commit.
        """
        if order.status == 'cancelled':
            raise PaymentValidationError('No se puede editar un pedido cancelado')

        # Cantidad 0 o ausente = eliminar ese producto. Negativos se dejan pasar
        # para que add_items_to_order los rechace con su error de validación.
        items_data = [it for it in items_data if it.get('quantity', 1) != 0]

        prev_snapshots = {item.product_name: item.modifiers_snapshot for item in order.items}

        # Eliminar items actuales para reconstruirlos desde el request.
        for item in list(order.items):
            db.session.delete(item)
        db.session.flush()

        total, validated_items = OrderService.add_items_to_order(
            order, items_data, restaurant_id)
        db.session.flush()

        # Conservar modificadores de productos que ya estaban y no se borraron.
        # Recargamos los items desde la DB: la colección order.items en memoria
        # aún contiene los viejos marcados para borrado.
        fresh_items = OrderItem.query.filter_by(order_id=order.id).all()
        for item in fresh_items:
            if item.product_name in prev_snapshots and not item.modifiers_snapshot:
                item.modifiers_snapshot = prev_snapshots[item.product_name]

        order.total = total

        # Edición de pago: el usuario confirmó el modal de pago en la pantalla
        # de edición → sobreescribir con el nuevo método/monto.
        if payment_method:
            OrderService._apply_payment(order, payment_method, amount_received)
        # Sin edición de pago: si ya se cobró en efectivo, recalcular el cambio.
        elif order.payment_method == 'cash' and order.amount_received is not None:
            if order.amount_received < total:
                db.session.rollback()
                raise PaymentValidationError(
                    f'El nuevo total (${total:,}) supera el monto recibido '
                    f'(${order.amount_received:,}). Ajusta el pago o cancela y rehaz la venta.'
                )
            order.change_due = order.amount_received - total

        db.session.commit()
        return total, validated_items

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
    def _apply_payment(order, method, amount_received=None):
        """Valida y aplica los campos de pago sobre un pedido (sin commit).

        Comparte las reglas de efectivo/caja entre `record_payment` (nuevo
        pago) y `update_order_payment` (sobreescribir en edición).
        """
        if method not in OrderService.PAYMENT_METHODS:
            raise PaymentValidationError('Método de pago inválido')

        if order.status == 'cancelled':
            raise PaymentValidationError('No se puede registrar un pago en un pedido cancelado')

        if method in OrderService.CASH_METHODS:
            received = amount_received
            try:
                received = int(received)
            except (TypeError, ValueError):
                raise PaymentValidationError('Debes indicar cuánto recibiste del cliente')
            if received <= 0:
                raise PaymentValidationError('El monto recibido debe ser mayor a 0')
            if received < order.total:
                falta = order.total - received
                raise PaymentValidationError(f'Falta dinero: ${falta:,}')
            change = received - order.total
            order.amount_received = received
            order.change_due = change
        else:
            # Métodos no-caja: ignorar cualquier monto que venga del request.
            order.amount_received = None
            order.change_due = None

        order.payment_method = method
        order.paid_at = datetime.now(timezone.utc)

    @staticmethod
    def record_payment(order, method, amount_received=None, change_due=None, actor=None):
        """
        Registrar el pago de un pedido (modal caja registradora).

        Reglas (server-side, no confiar solo en la UI):
        - `method` debe ser uno de: cash | nequi | bancolombia | card.
        - Un pedido cancelado nunca puede recibir pago.
        - Un pedido que ya tiene pago registrado NO puede sobreescribirse
          (idempotencia: doble clic / reintento de red / modal reabierto).
        - Efectivo: exige `amount_received >= order.total`, calcula el cambio
          y lanza PaymentValidationError si falta dinero.
        - Nequi/Bancolombia/Tarjeta: solo registran el método; los montos que
          pudieran venir en el request se fuerzan a None.

        Lanza PaymentValidationError (400) o PaymentValidationError con
        status_code=409 si el pedido ya tiene pago.

        Devuelve (order, change_due) tras commit.
        """
        if order.payment_method is not None:
            raise PaymentValidationError(
                'Este pedido ya tiene un pago registrado',
                status_code=409,
            )

        OrderService._apply_payment(order, method, amount_received)
        db.session.commit()

        return order, order.change_due

    @staticmethod
    def update_order_payment(order, method, amount_received=None, change_due=None, actor=None):
        """
        Sobre-escribir el pago de un pedido (edición de venta).

        A diferencia de `record_payment`, aquí el pedido PUEDE tener pago ya
        registrado: se reemplaza con los nuevos valores. Si el pedido no tenía
        pago, actúa igual que `record_payment`.

        Lanza PaymentValidationError (400). Devuelve (order, change_due).
        """
        OrderService._apply_payment(order, method, amount_received)
        db.session.commit()

        return order, order.change_due

    @staticmethod
    def cancel_order(order):
        """
        Cancel an order (set status to 'cancelled') and commit.

        Returns (True, None) or (False, error_message).
        Permite cancelar pedidos pendientes, confirmados y entregados.
        """
        if order.status == 'cancelled':
            return False, 'Este pedido ya fue cancelado'
        order.status = 'cancelled'
        db.session.commit()
        return True, None

    @staticmethod
    def delete_order(order):
        """
        Delete an order permanently.

        Returns (True, None) or (False, error_message).
        Solo permite eliminar pedidos cancelados o entregados.
        """
        if order.status not in ['cancelled', 'delivered']:
            return False, 'Solo se pueden eliminar pedidos cancelados o entregados'
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
            'payment_method': order.payment_method,
            'amount_received': order.amount_received,
            'change_due': order.change_due,
            'paid_at': order.paid_at.isoformat() if order.paid_at else None,
            'created_at': order.created_at.isoformat() if order.created_at else None
        }

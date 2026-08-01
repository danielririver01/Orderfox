import json
import requests
from flask import current_app
from app.models import Order, Restaurant, OrderItem, Table
from app.utils.timezone import to_colombia


def notify_new_order(order_id):
    app = current_app._get_current_object()
    try:
        with app.app_context():
            order = Order.query.get(order_id)
            if not order:
                return

            restaurant = Restaurant.query.get(order.restaurant_id)
            if not restaurant or not restaurant.ntfy_topic:
                return

            items = OrderItem.query.filter_by(order_id=order.id).all()
            table = Table.query.get(order.table_id) if order.table_id else None

            num = order.order_number.replace('ORD-', '')
            lines = [f"*Pedido #{num}*"]
            lines.append(f"*Cliente:* {order.customer_name}")
            if order.customer_phone:
                lines.append(f"*Teléfono:* {order.customer_phone}")
            if table:
                lines.append(f"*Mesa:* {table.name}")
            lines.append("")
            lines.append("*Productos:*")
            for item in items:
                line = f"• {item.product_name} x{item.quantity}"
                if item.modifiers_snapshot:
                    try:
                        mods = json.loads(item.modifiers_snapshot)
                        extras = [m.get('name', '') for m in mods if m.get('name')]
                        if extras:
                            line += f" ({', '.join(extras)})"
                    except json.JSONDecodeError:
                        pass
                lines.append(line)
            lines.append("")
            lines.append(f"*Total:* ${order.total:,}")

            customer_notes = _extract_customer_notes(order.notes)
            if customer_notes:
                lines.append("")
                lines.append(f"*Notas:* {customer_notes}")

            source = "Menú digital QR" if not order.table_id else "Menú de mesa"
            lines.append("")
            lines.append(f"_{source}_")

            created = order.created_at
            local = to_colombia(created)
            if local is not None:
                fecha = local.strftime("%d/%m/%Y - %I:%M %p").lstrip("0").replace(" 0", " ")
                lines.append(fecha)

            ntfy_base = app.config.get('NTFY_BASE_URL', 'https://ntfy.sh')
            requests.post(
                f"{ntfy_base}/{restaurant.ntfy_topic}",
                data="\n".join(lines),
                headers={
                    'Title': f"Pedido #{num} - {restaurant.name}",
                    'Priority': '4',
                    'Tags': 'bell',
                    'Content-Type': 'text/plain; charset=utf-8',
                },
                timeout=10,
            )

    except Exception as e:
        app.logger.error(f"Error sending new order notification: {e}")


def _extract_customer_notes(notes):
    if not notes:
        return None
    if "\n---\n" in notes:
        return notes.split("\n---\n", 1)[1].strip()
    return notes.strip()

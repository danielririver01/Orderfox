import json

import requests
from flask import current_app

from app.models import Order, OrderItem, Restaurant, Table
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

    except Exception as e:  # noqa: BLE001 — best-effort: el push nunca rompe el flujo
        app.logger.error(f"Error sending new order notification: {e}")


def _extract_customer_notes(notes):
    if not notes:
        return None
    if "\n---\n" in notes:
        return notes.split("\n---\n", 1)[1].strip()
    return notes.strip()


# ── Notificaciones de reservas (v1.5, feature/reservas) ──────────────────

def _post_ntfy(restaurant, title, body, priority='3', tags='bell'):
    """Envía una notificación ntfy al canal del restaurante. Best-effort:
    nunca propaga la excepción (el flujo de reservas no debe romperse por
    un fallo del canal de push)."""
    if not restaurant or not restaurant.ntfy_topic:
        return
    app = current_app._get_current_object()
    try:
        ntfy_base = app.config.get('NTFY_BASE_URL', 'https://ntfy.sh')
        requests.post(
            f"{ntfy_base}/{restaurant.ntfy_topic}",
            data=body,
            headers={
                'Title': title,
                'Priority': priority,
                'Tags': tags,
                'Content-Type': 'text/plain; charset=utf-8',
            },
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001 — best-effort: el push nunca rompe el flujo
        app.logger.error(f"Error sending ntfy notification ({title}): {e}")


def _fmt_reservation_date(res):
    """'Viernes 18/09' para una reserva (fecha ya en hora Colombia)."""
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    return f"{dias[res.reservation_date.weekday()]} {res.reservation_date.strftime('%d/%m')}"


def _fmt_reservation_time(res):
    """'8:00 pm' para una reserva."""
    return res.reservation_time.strftime('%I:%M %p').lstrip('0').lower()


def notify_new_reservation(reservation):
    """Restaurante: llegó una nueva solicitud de reserva."""
    restaurant = Restaurant.query.get(reservation.restaurant_id)
    note = f"\nNota: {reservation.customer_note}" if reservation.customer_note else ""
    body = (
        f"{reservation.customer_name} · {reservation.party_size} personas\n"
        f"{_fmt_reservation_date(reservation)} {_fmt_reservation_time(reservation)}"
        f"{note}\n\n"
        f"Confirma o rechaza desde el panel Velzia."
    )
    _post_ntfy(restaurant, "Reserva nueva - requiere confirmacion", body,
               priority='4', tags='bell')


def notify_reservation_confirmed(reservation):
    """Restaurante: registro de que confirmó la reserva (traza en su canal)."""
    restaurant = Restaurant.query.get(reservation.restaurant_id)
    body = (
        f"{reservation.customer_name} · {reservation.party_size} personas · "
        f"{_fmt_reservation_date(reservation)} {_fmt_reservation_time(reservation)}"
    )
    _post_ntfy(restaurant, "Reserva confirmada", body, priority='3', tags='white_check_mark')


def notify_reservation_rejected(reservation):
    """Restaurante: registro del rechazo (la mesa queda libre)."""
    restaurant = Restaurant.query.get(reservation.restaurant_id)
    motivo = f"\nMotivo: {reservation.rejection_reason}" if reservation.rejection_reason else ""
    body = (
        f"{reservation.customer_name} · "
        f"{_fmt_reservation_date(reservation)} {_fmt_reservation_time(reservation)}"
        f"{motivo}"
    )
    _post_ntfy(restaurant, "Reserva rechazada", body, priority='3', tags='no_entry_sign')


def notify_reservation_reminder(restaurant, reservation):
    """Restaurante: recordatorio automático de reserva próxima."""
    body = (
        f"{reservation.customer_name} · {reservation.party_size} personas · "
        f"hoy {_fmt_reservation_time(reservation)}\n"
        f"Prepara la mesa: {reservation.table.name if reservation.table else 'N/A'}"
    )
    _post_ntfy(restaurant, "Recordatorio de reserva", body, priority='3', tags='alarm_clock')

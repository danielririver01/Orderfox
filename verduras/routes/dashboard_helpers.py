"""Helpers del dashboard POS — formato es-CO y guard de sesión.

Extraído de `dashboard.py` sin cambios de comportamiento (Etapa 1 del
refactor orch-refine-code). Las rutas solo orquestan; el formato vive aquí.
"""
from ..services.pos_auth import current_pos_business


def _fmt_cop(value) -> str:
    """$1.234.567,00 — formato es-CO (punto miles, coma decimales)."""
    return (f'${value:,.2f}'.replace(',', 'X')
            .replace('.', ',').replace('X', '.'))


def _fmt_short(value) -> str:
    """$1.235 — pesos cerrados es-CO para paneles/KPIs (sin ,00)."""
    return f'${int(round(float(value))):,}'.replace(',', '.')


def _sale_for_ticket(sale) -> dict:
    """Payload mínimo para pintar/imprimir el ticket en el navegador."""
    return {
        'sale_number': sale.sale_number,
        'customer_name': sale.customer_name or '',
        'payment_method': sale.payment_method,
        'amount_received': (_fmt_cop(sale.amount_received)
                            if sale.amount_received is not None else None),
        'change_due': (_fmt_cop(sale.change_due)
                       if sale.change_due is not None else None),
        'total': _fmt_cop(sale.total),
        'items': [
            {
                'name': i.product_name,
                'qty': str(i.quantity.normalize()),
                'unit': i.unit,
                'line_total': _fmt_cop(i.line_total),
            }
            for i in sale.items
        ],
    }


def _pos_clientes_guard(slug):
    """Business con sesión o respuesta 401 lista. None si no hay sesión."""
    business = current_pos_business()
    if business is None or business.slug != slug:
        return None
    return business

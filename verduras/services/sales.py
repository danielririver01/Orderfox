"""
Servicio de ventas del vertical Verduras (Semana 2).

Reusa los patrones probados de velzia core sin duplicar código de core:
- Idempotencia de pedidos (v1.5): clave por intento + constraint único;
  la carrera entre requests concurrentes se resuelve con IntegrityError
  y devolviendo la venta original.
- Numeración atómica diaria: row lock `with_for_update()` (patrón
  OrderCounter de core) → V-YYYYMMDD-001, 002, ...
- Anti-abuso de pedidos públicos: honeypot, time-to-submit ≥ 3s y
  3/min por IP con ban de 10 min (patrón OrderRateLimiter de core,
  re-implementado contra verduras_sales porque core no debe conocer
  tablas del módulo).

Toda la lógica vive aquí; las rutas solo orquestan (convención del repo).
"""
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app.models import db
from verduras.models import VerdurasProduct
from verduras.models_sales import (
    PAYMENT_METHODS,
    SALE_STATUSES,
    SALE_TYPES,
    VerdurasBusinessSettings,
    VerdurasSale,
    VerdurasSaleCounter,
    VerdurasSaleItem,
)

_CENTS = Decimal('0.01')
# Precisión de báscula: 1 gramo (0.001 kg).
_MILLIS = Decimal('0.001')

# Honeypot: el frontend incluye un campo trampa invisible; si llega con
# contenido, quien llena el formulario no es un humano (patrón de core).
HONEYPOT_FIELD = 'user_secondary_email'
# Time-to-submit mínimo en segundos (anti-bot sin JS).
MIN_TIME_TO_SUBMIT = 3.0

_PHONE_RE = re.compile(r'^\+?\d{7,15}$')


class VerdurasValidationError(ValueError):
    """Datos inválidos o regla de negocio incumplida."""


class VerdurasNotFoundError(LookupError):
    """Recurso inexistente (o de otro business)."""


# ── Rate limiting (patrón OrderRateLimiter de core, contra ventas) ──


class SaleRateLimiter:
    """Anti-ráfaga: máx 3 pedidos/min por IP+business; ban de 10 min."""

    MAX_SALES_PER_MINUTE = 3
    BAN_DURATION_MINUTES = 10

    @staticmethod
    def _recent_count(business_id, ip, minutes):
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return VerdurasSale.query.filter(
            VerdurasSale.business_id == business_id,
            VerdurasSale.ip_address == ip,
            VerdurasSale.created_at >= since,
            VerdurasSale.status.in_(('pending', 'completed')),
        ).count()

    @classmethod
    def should_block(cls, business_id, ip):
        """Returns: (should_block: bool, message: str|None, wait_seconds: int|None)."""
        per_minute = cls._recent_count(business_id, ip, minutes=1)
        if per_minute >= cls.MAX_SALES_PER_MINUTE:
            return True, 'Demasiados pedidos seguidos. Espera unos minutos.', 600
        banned = cls._recent_count(business_id, ip,
                                   minutes=cls.BAN_DURATION_MINUTES)
        if banned >= cls.MAX_SALES_PER_MINUTE:
            return True, ('Sistema de seguridad activado: espera unos '
                          'minutos antes de intentar de nuevo.'), 600
        return False, None, None


# ── Helpers de validación ───────────────────────────────────


def _parse_quantity(value, unit):
    """Cantidad en la unidad del producto; kg/lb con precisión de gramo."""
    if value is None:
        raise VerdurasValidationError('La cantidad es requerida')
    try:
        raw = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(f'Cantidad inválida: {value!r}')
    if raw <= 0:
        raise VerdurasValidationError('La cantidad debe ser mayor a 0')
    qty = raw.quantize(_MILLIS, rounding=ROUND_HALF_UP)
    if qty == 0:
        # Ej: 0.0004 kg se redondea a cero → mensaje útil en vez de 'total 0'.
        raise VerdurasValidationError('Cantidad mínima: 0.001 (1 gramo)')
    if unit == 'unidad' and qty != qty.to_integral_value():
        raise VerdurasValidationError(
            'Para productos por unidad la cantidad debe ser entera')
    return qty


def _parse_price(value):
    try:
        price = Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise VerdurasValidationError(f'Precio inválido: {value!r}')
    if price <= 0:
        raise VerdurasValidationError('El precio debe ser mayor a 0')
    return price


def _normalize_name(name) -> str:
    if not name or not str(name).strip():
        raise VerdurasValidationError('El nombre es requerido')
    return str(name).strip()


def _parse_bool(value) -> bool:
    """Tolera booleans JSON y strings ('true'/'1'/'on')."""
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'on')
    return bool(value)


def _parse_day(value, field: str):
    """Fecha 'YYYY-MM-DD' → date; vacío → None."""
    if value is None or value == '':
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').replace(
            tzinfo=timezone.utc).date()
    except ValueError:
        raise VerdurasValidationError(
            f"Fecha inválida en '{field}' (usa YYYY-MM-DD)")


def _clean_phone(phone) -> str:
    """Dígitos con código de país, sin '+'. Vacío = no enviado (opcional)."""
    if not phone:
        return ''
    clean = re.sub(r'[^\d+]', '', str(phone))
    if not _PHONE_RE.match(clean):
        raise VerdurasValidationError('El número de WhatsApp no es válido')
    return clean.lstrip('+')


# ── Settings del business ───────────────────────────────────


def get_settings(business_id: int) -> VerdurasBusinessSettings:
    """Devuelve la config del business, creándola con defaults si no existe."""
    row = db.session.get(VerdurasBusinessSettings, business_id)
    if row is None:
        row = VerdurasBusinessSettings(business_id=business_id)
        db.session.add(row)
        db.session.commit()
    return row


def update_settings(business_id: int, data: dict) -> VerdurasBusinessSettings:
    row = get_settings(business_id)
    if 'whatsapp_phone' in data:
        row.whatsapp_phone = (
            _clean_phone(data['whatsapp_phone'])
            if data['whatsapp_phone'] else None)
    if 'is_open' in data:
        row.is_open = _parse_bool(data['is_open'])
    if 'delivery_enabled' in data:
        row.delivery_enabled = _parse_bool(data['delivery_enabled'])
    db.session.commit()
    return row


def build_whatsapp_link(business_id: int, sale: VerdurasSale) -> str | None:
    """
    URL `wa.me` con el resumen de la venta preformateado (patrón de core:
    el mensaje lo envía el cliente desde su WhatsApp; no hay API oficial).

    Requiere whatsapp_phone en settings; sin él devuelve None (el frontend
    oculta el botón, igual que core).
    """
    settings = get_settings(business_id)
    if not settings.whatsapp_phone:
        return None

    lines = [
        f'*Pedido {sale.sale_number}*',
        f'Cliente: {sale.customer_name or "—"}',
    ]
    for item in sale.items:
        qty = item.quantity.normalize()
        lines.append(
            f'• {qty} {item.unit} {item.product_name} — '
            f'${item.line_total:,.2f}'
        )
    lines.append(f'*Total: ${sale.total:,.2f}*')
    if sale.sale_type == 'delivery' and sale.delivery_address:
        lines.append(f'Dirección: {sale.delivery_address}')

    message = '\n'.join(lines)
    return f'https://wa.me/{settings.whatsapp_phone}?text={_uq(message)}'


def _uq(text: str) -> str:
    """URL-encode mínimo sin importar urllib en el hot path."""
    from urllib.parse import quote
    return quote(text)


# ── Numeración atómica (patrón OrderCounter de core) ────────


def generate_sale_number(business_id: int) -> str:
    """V-YYYYMMDD-NNN con row lock; safe bajo concurrencia.

    Fecha en UTC (regla del repo): en Colombia (UTC-5) `date.today()`
    cambiaría de día a las 7pm locales y desalinearía los contadores.
    """
    today = datetime.now(timezone.utc).date()
    counter = VerdurasSaleCounter.query.filter_by(
        business_id=business_id, date=today
    ).with_for_update().first()
    if counter is None:
        counter = VerdurasSaleCounter(business_id=business_id, date=today,
                                      last_number=0)
        db.session.add(counter)
    counter.last_number += 1
    return f'V-{today.strftime("%Y%m%d")}-{counter.last_number:03d}'


# ── Creación de ventas ──────────────────────────────────────


def find_by_idempotency_key(business_id: int, key):
    if not key or len(key) > 64:
        return None
    return VerdurasSale.query.filter_by(
        business_id=business_id, idempotency_key=key).first()


def create_sale(business_id: int, items_data: list, *, sale_type: str = 'walk_in',
                customer_name: str = '', customer_phone: str = '',
                delivery_address: str | None = None,
                payment_method: str | None = None,
                amount_received=None,
                client_id=None,
                idempotency_key: str | None = None,
                ip_address: str | None = None,
                skip_open_check: bool = False) -> tuple[VerdurasSale, bool]:
    """
    Crea una venta por peso con snapshot de precios. Returns: (sale, created).

    - items_data: [{'product_id': int, 'quantity': '0.500'|0.5|Decimal}, ...]
      El precio unitario se toma SIEMPRE del catálogo (never trust client).
    - walk_in: venta de mostrador (skip_open_check=True lo permite aunque
      el negocio esté marcado cerrado; el tendero atiende igual).
    - delivery: pedido público → valida abierto + domicilio habilitado.
    - Idempotencia: misma clave devuelve la venta original (created=False).
    """
    sale_type = str(sale_type or '').strip().lower()
    if sale_type not in SALE_TYPES:
        raise VerdurasValidationError(
            f"Tipo de venta inválido: '{sale_type}'. Válidos: {', '.join(SALE_TYPES)}")

    # Método de pago (v1 POS rediseñado): lista cerrada, sin strings
    # inventados. None = venta vieja / no especificado (columna nullable).
    payment_method = (str(payment_method or '').strip().lower() or None)
    if payment_method is not None and payment_method not in PAYMENT_METHODS:
        raise VerdurasValidationError(
            f"Método de pago inválido: '{payment_method}'. "
            f"Válidos: {', '.join(PAYMENT_METHODS)}")

    # Libreta exige dueño de la deuda (la ruta lo pide primero en UX; aquí
    # el guard autoritativo: sin cliente no hay a quién cargarle).
    client_row_id = None
    if payment_method == 'libreta':
        if client_id in (None, ''):
            raise VerdurasValidationError(
                'La venta con libreta exige un cliente')
        from verduras.services import clientes as clientes_svc
        try:
            cid = int(client_id)
        except (TypeError, ValueError):
            raise VerdurasValidationError('Cliente inválido')
        try:
            clientes_svc.require_client(business_id, cid)  # 404 si ajeno
        except LookupError as e:
            raise VerdurasNotFoundError(str(e))
        client_row_id = cid
    elif client_id not in (None, ''):
        raise VerdurasValidationError(
            'El cliente solo aplica a ventas con libreta')

    settings = get_settings(business_id)

    # Puertas abiertas para delivery (walk-in en mostrador siempre pasa).
    if sale_type == 'delivery' and not skip_open_check:
        if not settings.is_open:
            raise VerdurasValidationError(
                'El negocio está cerrado en este momento. ¡Vuelve pronto!')
        if not settings.delivery_enabled:
            raise VerdurasValidationError('Domicilios temporalmente desactivados.')

    # Idempotencia (v1.5): replay → venta original.
    idem_key = (idempotency_key or '').strip()[:64] or None
    if idem_key:
        existing = find_by_idempotency_key(business_id, idem_key)
        if existing:
            return existing, False

    if not items_data or not isinstance(items_data, list):
        raise VerdurasValidationError('La venta no tiene items')

    product_ids = [i.get('product_id') for i in items_data
                   if isinstance(i, dict) and i.get('product_id')]
    products = VerdurasProduct.query.filter(
        VerdurasProduct.id.in_(product_ids),
        VerdurasProduct.business_id == business_id,
        VerdurasProduct.is_active.is_(True),
    ).all() if product_ids else []
    products_map = {p.id: p for p in products}

    sale = VerdurasSale(
        business_id=business_id,
        sale_number='PENDING',  # temporal; se asigna con el contador
        sale_type=sale_type,
        # Nombre opcional (venta de mostrador rápida): espacios → ''. Solo
        # se valida si el cliente lo envió con contenido.
        customer_name=_normalize_name(customer_name)
        if (customer_name or '').strip() else '',
        customer_phone=_clean_phone(customer_phone) if customer_phone else '',
        delivery_address=(delivery_address or '').strip() or None,
        payment_method=payment_method,
        client_id=client_row_id,
        idempotency_key=idem_key,
        ip_address=ip_address,
        status='pending',
        total=Decimal('0.00'),
    )

    total = Decimal('0.00')
    for idx, item_data in enumerate(items_data):
        if not isinstance(item_data, dict):
            raise VerdurasValidationError(f'Item #{idx + 1} inválido')
        product = products_map.get(item_data.get('product_id'))
        if product is None:
            raise VerdurasNotFoundError(
                f'Producto {item_data.get("product_id")} no disponible')
        qty = _parse_quantity(item_data.get('quantity'), product.unit)
        unit_price = _parse_price(product.current_price)
        line_total = (unit_price * qty).quantize(_CENTS, rounding=ROUND_HALF_UP)
        sale.items.append(VerdurasSaleItem(
            product_id=product.id,
            product_name=product.name,
            unit=product.unit,
            unit_price=unit_price,
            quantity=qty,
            line_total=line_total,
        ))
        total += line_total

    if total <= 0:
        raise VerdurasValidationError('El total de la venta debe ser mayor a 0')

    # Cupo de crédito (fiados v2): la compra a libreta solo cabe dentro
    # del cupo disponible de la cuenta. Sin cupo (NULL) queda como siempre.
    if payment_method == 'libreta':
        from verduras.services import clientes as clientes_svc
        try:
            clientes_svc.check_credit_limit(business_id, client_row_id, total)
        except clientes_svc.ClientesValidationError as e:
            raise VerdurasValidationError(str(e))

    sale.total = total
    # Control de caja (solo efectivo): lo recibido debe cubrir el total y
    # las vueltas se calculan, nunca se inventan. Otros métodos lo ignoran.
    if payment_method == 'efectivo' and amount_received not in (None, ''):
        try:
            received = Decimal(str(amount_received)).quantize(_CENTS)
        except (InvalidOperation, ValueError):
            raise VerdurasValidationError(
                f'Monto recibido inválido: {amount_received!r}')
        if received <= 0:
            raise VerdurasValidationError(
                'El monto recibido debe ser mayor a 0')
        if received < total:
            raise VerdurasValidationError(
                f'Faltan ${(total - received):,.0f}: recibido '
                f'${received:,.0f} para un total de ${total:,.0f}')
        sale.amount_received = received
        sale.change_due = (received - total).quantize(_CENTS)
    sale.sale_number = generate_sale_number(business_id)
    db.session.add(sale)
    try:
        db.session.commit()
    except IntegrityError:
        # Carrera de idempotencia: el constraint único frenó al segundo
        # request; devolver el ganador (patrón create_order_idempotent).
        db.session.rollback()
        if idem_key:
            existing = find_by_idempotency_key(business_id, idem_key)
            if existing:
                return existing, False
        raise
    return sale, True


# ── Transiciones de estado ──────────────────────────────────


def mark_completed(business_id: int, sale_id: int) -> VerdurasSale:
    return _transition(business_id, sale_id, 'completed',
                       'completed_at', datetime.now(timezone.utc))


def mark_cancelled(business_id: int, sale_id: int) -> VerdurasSale:
    return _transition(business_id, sale_id, 'cancelled',
                       'cancelled_at', datetime.now(timezone.utc))


def _transition(business_id, sale_id, new_status, ts_field, ts_value):
    sale = get_sale(business_id, sale_id)
    if sale is None:
        raise VerdurasNotFoundError('Venta no encontrada')
    if sale.status == new_status:
        return sale  # idempotente
    if sale.status not in ('pending',):
        raise VerdurasValidationError(
            f'No se puede pasar de {sale.status} a {new_status}')
    sale.status = new_status
    setattr(sale, ts_field, ts_value)
    db.session.commit()
    return sale


def get_sale(business_id: int, sale_id: int) -> VerdurasSale | None:
    """Anti-IDOR: solo ventas del business dado."""
    sale = db.session.get(VerdurasSale, sale_id)
    if sale is None or sale.business_id != business_id:
        return None
    return sale


def list_sales(business_id: int, status: str | None = None,
               date_from=None, date_to=None) -> list[VerdurasSale]:
    """date_from/date_to aceptan date o string 'YYYY-MM-DD' (rutas finas)."""
    query = VerdurasSale.query.filter_by(business_id=business_id)
    if status:
        if status not in SALE_STATUSES:
            raise VerdurasValidationError(f"Estado inválido: '{status}'")
        query = query.filter_by(status=status)
    day_from = _parse_day(date_from, 'date_from')
    day_to = _parse_day(date_to, 'date_to')
    if day_from:
        start = datetime.combine(day_from, datetime.min.time(),
                                 tzinfo=timezone.utc)
        query = query.filter(VerdurasSale.created_at >= start)
    if day_to:
        end = datetime.combine(day_to, datetime.max.time(),
                               tzinfo=timezone.utc)
        query = query.filter(VerdurasSale.created_at <= end)
    return query.order_by(VerdurasSale.created_at.desc()).all()


# ── Guards anti-abuso (llamar desde la ruta antes de create_sale) ──


def check_public_guards(data: dict, business_id: int, ip: str | None):
    """Honeypot + time-to-submit + rate limit para pedidos públicos.

    Returns: (error_response_dict|None, status_code|None) → si hay error,
    la ruta devuelve eso tal cual; si es None, continuar.
    """
    # 1. Honeypot
    if data.get(HONEYPOT_FIELD):
        return ({'success': False,
                 'error': 'Actividad sospechosa detectada.'}, 403)

    # 2. Time-to-submit: el frontend marca t0 al abrir el checkout.
    try:
        t0 = float(data.get('_t0') or 0)
    except (TypeError, ValueError):
        t0 = 0.0  # valor corrupto: se comporta como cliente sin JS (pasa)
    elapsed = time.time() - t0 if t0 > 0 else 999
    if elapsed < MIN_TIME_TO_SUBMIT:
        return ({'success': False,
                 'error': '¡Uy, vas muy rápido! Tómate un segundo para '
                          'revisar tus datos.'}, 429)

    # 3. Rate limit por IP
    blocked, message, wait = SaleRateLimiter.should_block(business_id, ip)
    if blocked:
        return ({'success': False, 'error': message,
                 'retry_after': wait}, 429)

    return None, None

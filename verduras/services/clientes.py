"""
Cuentas de fiado del vertical Verduras (libreta): clientes, abonos y saldo.

Filosofía (misma del módulo): la deuda NUNCA se almacena, se DERIVA como
fiados − abonos. Cada movimiento deja huella; el saldo siempre se puede
reconstruir. Sin roles en v1: nace desde la venta.

Toda la lógica vive aquí; las rutas solo orquestan (convención del repo).
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.models import db
from verduras.models_sales import (
    VerdurasAbono,
    VerdurasCliente,
    VerdurasSale,
)

_CENTS = Decimal('0.01')

# Método con que entra el dinero del abono (lista cerrada). La libreta no
# es método de abono: se abona la deuda, no se aumenta.
ABONO_METHODS = ('efectivo', 'transferencia', 'tarjeta')


class ClientesValidationError(ValueError):
    """Datos inválidos o regla de la cuenta incumplida."""


class ClientesNotFoundError(LookupError):
    """Cliente inexistente (o de otro business)."""


def _get_client(business_id: int, client_id: int) -> VerdurasCliente:
    client = db.session.get(VerdurasCliente, client_id)
    if client is None or client.business_id != business_id:
        raise ClientesNotFoundError('Cliente no encontrado')
    return client


def require_client(business_id: int, client_id: int) -> VerdurasCliente:
    """Cliente del negocio o ClientesNotFoundError (para otros servicios)."""
    return _get_client(business_id, client_id)


def get_or_create_client(business_id: int, name: str,
                         phone=None) -> VerdurasCliente:
    """Busca por nombre (único por negocio) o crea. Duplicado se reutiliza."""
    name = str(name or '').strip()
    if not name:
        raise ClientesValidationError('El nombre es requerido')
    existing = VerdurasCliente.query.filter_by(
        business_id=business_id, name=name).first()
    if existing is not None:
        return existing
    client = VerdurasCliente(
        business_id=business_id, name=name,
        phone=(str(phone or '').strip() or None),
    )
    db.session.add(client)
    try:
        db.session.commit()
    except IntegrityError:  # carrera: otro request lo creó primero
        db.session.rollback()
        existing = VerdurasCliente.query.filter_by(
            business_id=business_id, name=name).first()
        if existing is None:  # pragma: no cover — defensivo
            raise
        return existing
    return client


def _parse_monto(value) -> Decimal:
    try:
        monto = Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise ClientesValidationError(f'Monto inválido: {value!r}')
    if monto <= 0:
        raise ClientesValidationError('El monto debe ser mayor a 0')
    return monto


def saldo_cliente(business_id: int, client_id: int) -> Decimal:
    """Deuda viva: fiados no cancelados − abonos. Jamás negativa."""
    _get_client(business_id, client_id)
    fiados = db.session.query(func.sum(VerdurasSale.total)).filter(
        VerdurasSale.business_id == business_id,
        VerdurasSale.client_id == client_id,
        VerdurasSale.payment_method == 'libreta',
        VerdurasSale.status != 'cancelled',
    ).scalar()
    abonos = db.session.query(func.sum(VerdurasAbono.monto)).filter(
        VerdurasAbono.business_id == business_id,
        VerdurasAbono.client_id == client_id,
    ).scalar()
    saldo = (Decimal(str(fiados or 0)) - Decimal(str(abonos or 0)))
    return max(saldo, Decimal('0.00')).quantize(_CENTS)


def registrar_abono(business_id: int, client_id: int, monto,
                    note=None, method=None) -> VerdurasAbono:
    """Pago parcial contra la deuda. Mayor al saldo → 400 (no hay vueltas
    en abonos: se abona hasta el saldo, el resto es otra historia).
    `method` (v2): efectivo | transferencia | tarjeta; inválido → 400."""
    _get_client(business_id, client_id)
    monto = _parse_monto(monto)
    method = _parse_method(method)
    saldo = saldo_cliente(business_id, client_id)
    if monto > saldo:
        raise ClientesValidationError(
            f'El abono (${monto:,.0f}) supera la deuda (${saldo:,.0f})'
            .replace(',', '.'))
    abono = VerdurasAbono(
        business_id=business_id, client_id=client_id, monto=monto,
        note=(str(note or '').strip() or None), method=method,
    )
    db.session.add(abono)
    db.session.commit()
    return abono


def _parse_method(method) -> str | None:
    """Método del abono normalizado ('' → None, desconocido → error)."""
    if method in (None, ''):
        return None
    method = str(method).strip().lower()
    if method not in ABONO_METHODS:
        raise ClientesValidationError(
            'Método inválido (usa: ' + ', '.join(ABONO_METHODS) + ')')
    return method


def check_credit_limit(business_id: int, client_id: int,
                       new_charge) -> None:
    """Fiar solo cabe dentro del cupo (v2). Cupo NULL = sin techo (como
    siempre). Disponible = cupo − saldo vivo; la compra que lo exceda
    se rechaza ANTES de crear la venta (el fiado es dinero)."""
    client = _get_client(business_id, client_id)
    if client.credit_limit is None:
        return
    disponible = client.credit_limit - saldo_cliente(business_id, client_id)
    charge = Decimal(str(new_charge))
    if charge > disponible:
        raise ClientesValidationError(
            f'Supera el cupo de la libreta: disponible '
            f'${disponible:,.0f}'.replace(',', '.')
            + f', compra ${charge:,.0f}'.replace(',', '.') + '.')


def set_credit_limit(business_id: int, client_id: int,
                     limit=None) -> VerdurasCliente:
    """Cupo de crédito de la libreta (None/vacío = sin límite)."""
    client = _get_client(business_id, client_id)
    if limit in (None, ''):
        client.credit_limit = None
    else:
        try:
            value = Decimal(str(limit)).quantize(_CENTS,
                                                 rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            raise ClientesValidationError(f'Cupo inválido: {limit!r}')
        if value < 0:
            raise ClientesValidationError('El cupo no puede ser negativo')
        client.credit_limit = value
    db.session.commit()
    return client


def set_internal_note(business_id: int, client_id: int,
                      note=None) -> VerdurasCliente:
    """Nota interna del tendero sobre la cuenta (None/vacío la quita)."""
    client = _get_client(business_id, client_id)
    text = str(note or '').strip() or None
    if text and len(text) > 500:
        raise ClientesValidationError('La nota no puede pasar de 500 caracteres')
    client.internal_note = text
    db.session.commit()
    return client


def set_compromiso(business_id: int, client_id: int,
                   fecha=None) -> VerdurasCliente:
    """Fecha de compromiso de pago de la cuenta (None la quita)."""
    client = _get_client(business_id, client_id)
    if fecha in (None, ''):
        client.fecha_compromiso = None
    else:
        try:
            client.fecha_compromiso = datetime.strptime(
                str(fecha)[:10], '%Y-%m-%d').date()
        except ValueError:
            raise ClientesValidationError(
                f'Fecha inválida: {fecha!r} (usa AAAA-MM-DD)')
    db.session.commit()
    return client


def list_clientes(business_id: int) -> list[dict]:
    """Cuentas con saldo derivado, ordenadas por deuda (mayor primero).
    `saldo`/`credit_limit` salen como Decimal-string crudo: el formateo
    es-CO lo hace la ruta (dashboard_helpers) justo antes de renderizar."""
    rows = []
    for c in (VerdurasCliente.query.filter_by(business_id=business_id)
              .order_by(VerdurasCliente.name).all()):
        rows.append({
            'id': c.id, 'name': c.name, 'phone': c.phone,
            'is_active': bool(c.is_active),
            'fecha_compromiso': (c.fecha_compromiso.isoformat()
                                 if c.fecha_compromiso else None),
            'credit_limit': (str(c.credit_limit)
                             if c.credit_limit is not None else None),
            'saldo': str(saldo_cliente(business_id, c.id)),
        })
    rows.sort(key=lambda r: Decimal(r['saldo']), reverse=True)
    return rows


def resumen_fiados(business_id: int, cuentas: list[dict]) -> dict:
    """KPIs del panel (fiados v2), derivados de saldos ya calculados.

    Recibe las filas de list_clientes (saldo como Decimal-string crudo) y
    agrega: total por cobrar, abonos de hoy (Bogotá), cuentas con
    compromiso vencido y cupo total otorgado + uso. Cero SQL nuevo: la
    misma fuente de verdad que la tabla.
    """
    from verduras.services.caja import bogota_today

    today = bogota_today()
    hoy_iso = today.isoformat()
    total_por_cobrar = Decimal('0')
    con_saldo = 0
    vencidas = 0
    al_dia = 0
    cupo_total = Decimal('0')
    uso_cupo = Decimal('0')
    for c in cuentas:
        saldo = Decimal(c['saldo'])
        total_por_cobrar += saldo
        if saldo > 0:
            con_saldo += 1
            # Vencida SOLO si tiene compromiso pasado y sigue debiendo.
            # Sin compromiso no hay vencimiento posible.
            if c.get('fecha_compromiso') and c['fecha_compromiso'] < hoy_iso:
                vencidas += 1
            else:
                al_dia += 1
        else:
            al_dia += 1
        if c.get('credit_limit') is not None:
            cupo_total += Decimal(c['credit_limit'])
            uso_cupo += saldo
    abonos_hoy = (db.session.query(func.sum(VerdurasAbono.monto)).filter(
        VerdurasAbono.business_id == business_id,
        func.date(VerdurasAbono.registered_at) == hoy_iso,
    ).scalar() or 0)
    return {
        'total_por_cobrar': total_por_cobrar,
        'con_saldo': con_saldo,
        'vencidas': vencidas,
        'al_dia': al_dia,
        'cupo_total': cupo_total,
        'uso_cupo': uso_cupo,
        'abonos_hoy': Decimal(str(abonos_hoy)).quantize(_CENTS),
    }

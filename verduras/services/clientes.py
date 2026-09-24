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
                    note=None) -> VerdurasAbono:
    """Pago parcial contra la deuda. Mayor al saldo → 400 (no hay vueltas
    en abonos: se abona hasta el saldo, el resto es otra historia)."""
    _get_client(business_id, client_id)
    monto = _parse_monto(monto)
    saldo = saldo_cliente(business_id, client_id)
    if monto > saldo:
        raise ClientesValidationError(
            f'El abono (${monto:,.0f}) supera la deuda (${saldo:,.0f})'
            .replace(',', '.'))
    abono = VerdurasAbono(
        business_id=business_id, client_id=client_id, monto=monto,
        note=(str(note or '').strip() or None),
    )
    db.session.add(abono)
    db.session.commit()
    return abono


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
    """Cuentas con saldo derivado, ordenadas por deuda (mayor primero)."""
    rows = []
    for c in (VerdurasCliente.query.filter_by(business_id=business_id)
              .order_by(VerdurasCliente.name).all()):
        rows.append({
            'id': c.id, 'name': c.name, 'phone': c.phone,
            'is_active': bool(c.is_active),
            'fecha_compromiso': (c.fecha_compromiso.isoformat()
                                 if c.fecha_compromiso else None),
            'saldo': str(saldo_cliente(business_id, c.id)),
        })
    rows.sort(key=lambda r: Decimal(r['saldo']), reverse=True)
    return rows

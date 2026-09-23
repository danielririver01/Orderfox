"""
Escrituras de billing unificado — Ecosistema Multi-Mundos.

El User dueño es la ÚNICA fuente de verdad del billing: paga una
suscripción que cubre todos sus mundos. Toda escritura de ciclo (pago
aprobado, trial, cancelación, expiración) llega aquí, se aplica AL DUEÑO
y sincroniza hacia abajo las columnas equivalentes de Restaurant/Business,
que son solo caché de legibilidad (los reads delegan en
app/utils/subscription.py via _billing_view_for).

Regla de oro legacy: una fila SIN dueño se gobierna sola. Los callers
verifican el dueño antes de llamarnos; con dueño=None estos helpers son
no-op y el caller usa su camino directo de siempre (compatibilidad con
el piloto de verdulas y datos pre-migración).

Convención de transacción: las funciones hacen flush pero NO commit
(salvo el wallet, que es idempotente y commitea como toda su vida) — se
integran en la transacción del llamador.
"""
from datetime import datetime, timedelta, timezone

from flask import current_app

from app import db
from app.models import AITokenTransaction, Business, Restaurant
from app.utils.subscription import (
    _owner_carries_billing as _owner_carries_billing_impl,
)
from app.utils.subscription import (
    _resolve_owner as _resolve_owner_impl,
)
from app.utils.subscription import (
    _sync_billing_down as sync_billing_down,
)
from app.utils.subscription import (
    get_plan_limits,
    initialize_or_reset_token_wallet,
)

PAID_PLANS = ('emprendedor', 'crecimiento', 'elite')


def resolve_owner(subject):
    """User dueño de una fila Restaurant/Business (o None si es legacy sin
    dueño). Envoltorio público del resolver de app.utils.subscription."""
    return _resolve_owner_impl(subject)


def owner_carries_billing(owner):
    """True si el dueño YA tiene ciclo propio (gobierna sus filas).
    Espeja el criterio de lectura de _billing_view_for: los writes deben
    usar exactamente la misma frontera que los reads."""
    return _owner_carries_billing_impl(owner)


def row_has_live_cycle(row):
    """True si la fila tiene suscripción vigente (fecha futura). Una fila
    con ciclo vivo y dueño sin ciclo propio es legacy pura: su renovación
    extiende la fila (días restantes intactos), no arranca cuenta."""
    exp = _utc_aware(getattr(row, 'subscription_expires_at', None))
    return exp is not None and exp > datetime.now(timezone.utc)


def _utc_aware(dt):
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _plan_expires_at(owner, plan_type, now):
    """Expiración del dueño tras pagar `plan_type`: extiende desde la fecha
    vigente si aún no venció (conserva días pagados), o desde ahora.
    Mismo patrón que _finalize_payment de restaurantes."""
    duration = get_plan_limits(plan_type).get('duration_days', 30)
    current = _utc_aware(owner.subscription_expires_at)
    if current and current > now:
        return current + timedelta(days=duration)
    return now + timedelta(days=duration)


def activate_user_from_payment(owner, plan_type, payment_id=None):
    """Ciclo de PAGO a nivel User: sube de plan, activa la cuenta, extiende
    la expiración y sincroniza TODOS sus mundos (cachés) — un pago cubre
    todo. Reactiva lo dormido (is_active=True, dormant_at=None).

    Idempotencia callback↔webhook: la deja en el marcador de transacción
    de wallet (mp_payment_id, constraint único): si el pago ya quedó
    registrado, un reintento NO re-escribe el ciclo. Sin dueño: no-op
    (el caller usa su camino directo).
    """
    if owner is None:
        return None
    if payment_id and AITokenTransaction.query.filter_by(
        mp_payment_id=payment_id,
        type='topup_plan',
    ).first():
        return owner  # pago ya procesado (callback ↔ webhook)
    now = datetime.now(timezone.utc)
    if plan_type in PAID_PLANS:
        owner.plan_type = plan_type
    if owner.subscription_state in ('dormant', 'cancellation_pending'):
        owner.subscription_state = 'active'
    owner.subscription_expires_at = _plan_expires_at(owner, owner.plan_type, now)

    sync_billing_down(owner, set_active=True)
    for biz in Business.query.filter_by(owner_user_id=owner.id).all():
        biz.dormant_at = None
    if owner.restaurant_id:
        r = db.session.get(Restaurant, owner.restaurant_id)
        if r is not None:
            r.dormant_at = None
    db.session.flush()

    if payment_id:
        try:
            # Crédito de tokens del dueño (wallet nuevo O reset — ambos
            # caminos commitean su propia tx; sin restaurante el wallet es
            # no-op y el marcador de abajo queda como única evidencia).
            initialize_or_reset_token_wallet(
                owner, is_reset=True, mp_payment_id=payment_id)
        except Exception:
            current_app.logger.exception(
                "billing User: error en wallet del dueño %s", owner.id)
            db.session.rollback()
        # Marcador de idempotencia callback↔webhook: tx con mp_payment_id
        # (constraint UNIQUE). Cubre también el wallet recién creado (su tx
        # 'system_init' no registra el pago) y dueños sin restaurante.
        if not AITokenTransaction.query.filter_by(
            mp_payment_id=payment_id,
            type='topup_plan',
        ).first():
            db.session.add(AITokenTransaction(
                user_id=owner.id,
                type='topup_plan',
                amount=0,
                source='user_plan_payment',
                mp_payment_id=payment_id,
                description=f'Suscripción {owner.plan_type} — cuenta {owner.id}',
            ))
        db.session.flush()
    return owner


def propagate_row_renewal(row, effective_plan):
    """Renovación legacy por fila (dueño sin ciclo propio, fila con ciclo
    vivo): extiende la fila conservando sus días restantes y el dueño
    hereda el billing resultante como caché inicial — a partir de aquí el
    dueño tiene ciclo propio y las siguientes renovaciones ya pasan por
    activate_user_from_payment. No crea marcador de pago: esa
    idempotencia la maneja el caller (_finalize_payment)."""
    duration = get_plan_limits(effective_plan).get('duration_days', 30)
    now = datetime.now(timezone.utc)
    expires = _utc_aware(row.subscription_expires_at)
    if expires and expires > now:
        row.subscription_expires_at = expires + timedelta(days=duration)
    else:
        row.subscription_expires_at = now + timedelta(days=duration)
    if effective_plan in PAID_PLANS:
        row.plan_type = effective_plan
    owner = _resolve_owner_impl(row)
    if owner is not None:
        owner.plan_type = row.plan_type
        owner.subscription_expires_at = row.subscription_expires_at
        owner.subscription_state = row.subscription_state or 'active'
    db.session.flush()


def start_user_trial(owner, days=60):
    """Ciclo de TRIAL a nivel User: un solo reloj para todos los mundos.

    Marca el trial como usado y fija la expiración en el dueño (los mundos
    añadidos después NO renuevan el trial: si el dueño ya tiene ciclo
    activo, esto es no-op — el ciclo es del usuario, no de cada fila)."""
    if owner is None:
        return owner
    now = datetime.now(timezone.utc)
    current = _utc_aware(owner.subscription_expires_at)
    if current and current > now:
        # Ya tiene ciclo activo: no se toca (un solo reloj por cuenta).
        # La fila nueva se alinea al dueño para que ninguna caché muestre
        # un trial que no le corresponde.
        sync_billing_down(owner)
        db.session.flush()
        return owner
    if owner.has_used_trial:
        return owner
    owner.plan_type = 'trial'
    owner.subscription_state = 'active'
    owner.subscription_expires_at = now + timedelta(days=days)
    owner.has_used_trial = True
    sync_billing_down(owner)
    db.session.flush()
    return owner


def request_user_cancellation(owner, now=None):
    """Cancelación a nivel User: deja de renovar; el acceso continúa hasta
    la expiración (cancellation_pending). El scheduler pausará los mundos
    cuando la fecha pase."""
    if owner is None:
        return None
    owner.subscription_state = 'cancellation_pending'
    sync_billing_down(owner)
    db.session.flush()
    return owner


def resume_user_subscription(owner):
    """Reversa de cancelación pendiente (el dueño se arrepintió)."""
    if owner is None:
        return None
    if owner.subscription_state != 'cancellation_pending':
        return owner
    owner.subscription_state = 'active'
    sync_billing_down(owner)
    db.session.flush()
    return owner


def pause_user_worlds(owner, now):
    """Ciclo de EXPIRACIÓN (scheduler): cuenta vencida o cancelada → pausa
    TODOS los mundos del dueño. Nada se borra: datos preservados y
    dormant_at auditado en cada fila para la reactivación."""
    owner.subscription_state = 'dormant'
    sync_billing_down(owner, set_active=False)
    for biz in Business.query.filter_by(owner_user_id=owner.id).all():
        if biz.dormant_at is None:
            biz.dormant_at = now
    if owner.restaurant_id:
        r = db.session.get(Restaurant, owner.restaurant_id)
        if r is not None and r.dormant_at is None:
            r.dormant_at = now
    return owner

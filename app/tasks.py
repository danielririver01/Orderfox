from app import db, scheduler
from app.models import Restaurant, Order, DiscountCoupon
from datetime import datetime, timedelta, timezone
from flask import has_app_context, current_app
from app.services.order_service import log_event


def scan_business_events():
    """Escanea restaurantes en busca de BusinessEvents. Cada hora."""
    if has_app_context():
        return _perform_event_scan()
    else:
        with scheduler.app.app_context():
            return _perform_event_scan()


def _perform_event_scan():
    try:
        from app.services.insights.event_engine import scan_all_restaurants, auto_dismiss_expired
        dismissed = auto_dismiss_expired()
        results = scan_all_restaurants()
        current_app.logger.info(
            f"[{datetime.now(timezone.utc)}] "
            f"Events: scanned={results['scanned']}, created={results['events_created']}, "
            f"auto-dismissed={dismissed}"
        )
    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR in event scan: {e}")
def manage_subscription_lifecycle():
    """
    Gestiona el ciclo de vida de suscripciones SIN destruir datos.

    Estrategia (SaaS):
    - Las cuentas inactivas (is_active=False) NO se borran.
    - Tras INACTIVE_GRACE_DAYS días de inactividad, se marcan como 'dormant'
      (suspendidas, pero con todos sus datos preservados para reactivación).
    - Solo tras un período MUY largo (ver PURGE_AFTER_DAYS) se considera
      soft-delete, y nunca dentro de esta tarea por defecto.

    Programado diariamente a las 3:00 AM.
    """
    if has_app_context():
        return _perform_lifecycle()
    else:
        with scheduler.app.app_context():
            return _perform_lifecycle()


# Días de margen antes de marcar una cuenta inactiva como 'dormant'.
INACTIVE_GRACE_DAYS = 30


def _perform_lifecycle():
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=INACTIVE_GRACE_DAYS)
        current_app.logger.info(
            f"[{datetime.now(timezone.utc)}] Checking subscription lifecycle... "
            f"Dormant cutoff: {cutoff_time}"
        )

        # Cuentas inactivas (nunca pagaron o suspendidas manualmente) que llevan
        # más de INACTIVE_GRACE_DAYS días sin activarse → se marcan 'dormant'.
        # NUNCA se borra el restaurante ni sus datos.
        inactive_restaurants = Restaurant.query.filter(
            Restaurant.is_active == False,
            Restaurant.subscription_state != 'dormant',
            Restaurant.created_at < cutoff_time
        ).all()

        # Restaurantes con suscripción vencida más allá del grace period:
        # se suspenden (dormant) pero CON todos sus datos preservados.
        from app.utils.subscription import GRACE_PERIOD_DAYS
        grace_cutoff = datetime.now(timezone.utc) - timedelta(days=GRACE_PERIOD_DAYS)
        expired_restaurants = Restaurant.query.filter(
            Restaurant.is_active == True,
            Restaurant.subscription_state != 'dormant',
            Restaurant.subscription_state != 'cancellation_pending',
            Restaurant.subscription_expires_at.isnot(None),
            Restaurant.subscription_expires_at < grace_cutoff
        ).all()

        # Cancelaciones pendientes cuya fecha de expiración ya pasó:
        # pasan directamente a dormant (el usuario ya no tiene acceso).
        cancelled_expired = Restaurant.query.filter(
            Restaurant.subscription_state == 'cancellation_pending',
            Restaurant.subscription_expires_at.isnot(None),
            Restaurant.subscription_expires_at < datetime.now(timezone.utc)
        ).all()

        total = list(set(inactive_restaurants + expired_restaurants + cancelled_expired))

        if total:
            current_app.logger.info(
                f"[{datetime.now(timezone.utc)}] Found {len(total)} "
                f"accounts to mark dormant (data preserved)..."
            )
            count = 0
            now = datetime.now(timezone.utc)
            for restaurant in total:
                try:
                    restaurant.is_active = False
                    restaurant.subscription_state = 'dormant'
                    restaurant.dormant_at = now
                    count += 1
                except Exception as e:
                    current_app.logger.error(f"Error marking restaurant {restaurant.id} dormant: {e}")

            try:
                db.session.commit()
                current_app.logger.info(
                    f"[{datetime.now(timezone.utc)}] Lifecycle complete. "
                    f"Marked {count} restaurants as dormant (data preserved)."
                )
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"[{datetime.now(timezone.utc)}] Commit failed: {e}")
        else:
            current_app.logger.info(f"[{datetime.now(timezone.utc)}] No accounts to mark dormant.")

    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR in lifecycle task: {e}")


def expire_pending_orders():
    """
    Expira pedidos pendientes que han superado su tiempo de expiración.
    Se ejecuta cada hora para mantener los pedidos actualizados.
    """
    if has_app_context():
        return _perform_expiry()
    else:
        with scheduler.app.app_context():
            return _perform_expiry()

def _perform_expiry():
    try:
        now = datetime.now(timezone.utc)
        current_app.logger.info(f"[{now}] Checking pending order expiry...")
        
        # Buscar pedidos pendientes que han expirado
        expired_orders = Order.query.filter(
            Order.status == 'pending',
            Order.expires_at.isnot(None),
            Order.expires_at < now
        ).all()
        
        if expired_orders:
            current_app.logger.info(f"[{now}] Found {len(expired_orders)} expired pending orders. Expiring...")
            count = 0
            for order in expired_orders:
                try:
                    order.status = 'expired'
                    log_event(order.id, 'order_expired', actor_role='system')
                    count += 1
                except Exception as e:
                    current_app.logger.error(f"Error expiring order {order.id}: {e}")
            
            try:
                db.session.commit()
                current_app.logger.info(f"[{now}] Expiry complete. Expired {count} orders.")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"[{now}] Commit failed: {e}")
        else:
            current_app.logger.info(f"[{now}] No expired pending orders found.")

    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR in expiry task: {e}")


def expire_coupons():
    """Expira cupones pending que superaron su fecha de expiración."""
    if has_app_context():
        return _perform_coupon_expiry()
    else:
        with scheduler.app.app_context():
            return _perform_coupon_expiry()

def _perform_coupon_expiry():
    try:
        now = datetime.now(timezone.utc)
        expired = DiscountCoupon.query.filter(
            DiscountCoupon.status.in_(['pending', 'reserved']),
            DiscountCoupon.expires_at < now,
        ).all()
        for c in expired:
            c.status = 'expired'
        db.session.commit()
        if expired:
            current_app.logger.info(f"[{now}] Expired {len(expired)} coupons.")
    except Exception as e:
        current_app.logger.error(f"Coupon expiry error: {e}", exc_info=True)

def send_subscription_reminders():
    """Envía recordatorios de suscripción (días 5, 2 y 1 antes del vencimiento)."""
    if has_app_context():
        return _perform_reminders()
    else:
        with scheduler.app.app_context():
            return _perform_reminders()


def _perform_reminders():
    try:
        from app.services.reminder_service import send_subscription_reminders as _send
        sent = _send()
        current_app.logger.info(
            f"[{datetime.now(timezone.utc)}] Subscription reminders sent: {sent}"
        )
    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR in subscription reminders task: {e}")


def compute_platform_benchmarks():
    """
    Recalcula los benchmarks anónimos de la plataforma (medianas por cohorte,
    k-anonymity >= 5) que Copilot VZ usa para comparar el negocio del usuario.
    Diario a las 4:15 AM (después del lifecycle de las 3:00).
    """
    if has_app_context():
        return _perform_benchmarks()
    else:
        with scheduler.app.app_context():
            return _perform_benchmarks()


def _perform_benchmarks():
    try:
        from app.services.insights.benchmark_service import compute_benchmarks
        result = compute_benchmarks()
        current_app.logger.info(
            f"[{datetime.now(timezone.utc)}] Benchmarks computed: {result}"
        )
        return result
    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR in benchmarks task: {e}", exc_info=True)


def init_tasks(scheduler):
    # Gestionar ciclo de vida de suscripciones (sin borrado destructivo)
    if not scheduler.get_job('manage_subscription_lifecycle'):
        scheduler.add_job(
            id='manage_subscription_lifecycle',
            func=manage_subscription_lifecycle,
            trigger='cron',
            hour=3,
            minute=0
        )
    
    # Programar la tarea de expiración cada hora
    if not scheduler.get_job('expire_pending_orders'):
        scheduler.add_job(
            id='expire_pending_orders',
            func=expire_pending_orders,
            trigger='cron',
            minute=0  # Cada hora en punto
        )

    # Programar escaneo de BusinessEvents cada hora
    if not scheduler.get_job('scan_business_events'):
        scheduler.add_job(
            id='scan_business_events',
            func=scan_business_events,
            trigger='cron',
            minute=30,  # 30 minutos después de expire_pending_orders
        )

    # Expirar cupones vencidos cada hora
    if not scheduler.get_job('expire_coupons'):
        scheduler.add_job(
            id='expire_coupons',
            func=expire_coupons,
            trigger='cron',
            minute=45,
        )

    # Recordatorios de suscripción (diario 13:00 UTC = 8:00 AM Colombia).
    # Antes lo orquestaba n8n; ahora APScheduler envía los emails directo.
    if not scheduler.get_job('send_subscription_reminders'):
        scheduler.add_job(
            id='send_subscription_reminders',
            func=send_subscription_reminders,
            trigger='cron',
            hour=13,
            minute=0,
        )

    # Benchmarks anónimos para Copilot VZ (diario 4:15 AM).
    if not scheduler.get_job('compute_platform_benchmarks'):
        scheduler.add_job(
            id='compute_platform_benchmarks',
            func=compute_platform_benchmarks,
            trigger='cron',
            hour=4,
            minute=15,
        )

from app import db, scheduler
from app.models import Restaurant, Order, DiscountCoupon
from datetime import datetime, timedelta, timezone
from flask import has_app_context, current_app


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

def delete_inactive_accounts():
    """
    Elimina cuentas (Restaurantes) que están inactivas y fueron creadas hace más de 24 horas.
    Esta función está programada para ejecutarse todos los días a las 3:00 AM.
    """
    if has_app_context():
        return _perform_cleanup()
    else:
        with scheduler.app.app_context():
            return _perform_cleanup()

def _perform_cleanup():
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        current_app.logger.info(f"[{datetime.now(timezone.utc)}] Checking cleanup... Cutoff: {cutoff_time}")
        
        inactive_restaurants = Restaurant.query.filter(
            Restaurant.is_active == False,
            Restaurant.created_at < cutoff_time
        ).all()
        
        if inactive_restaurants:
            current_app.logger.info(f"[{datetime.now(timezone.utc)}] Found {len(inactive_restaurants)} inactive restaurants. Deleting...")
            count = 0
            for restaurant in inactive_restaurants:
                try:
                    db.session.delete(restaurant)
                    count += 1
                except Exception as e:
                    current_app.logger.error(f"Error deleting restaurant {restaurant.id}: {e}")
            
            try:
                db.session.commit()
                current_app.logger.info(f"[{datetime.now(timezone.utc)}] Cleanup complete. Deleted {count} records.")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"[{datetime.now(timezone.utc)}] Commit failed: {e}")
        else:
            current_app.logger.info(f"[{datetime.now(timezone.utc)}] No inactive accounts found.")

    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR in cleanup task: {e}")


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


def init_tasks(scheduler):
    # Programar la tarea para las 3:00 AM todos los días
    if not scheduler.get_job('delete_inactive_accounts'):
        scheduler.add_job(
            id='delete_inactive_accounts',
            func=delete_inactive_accounts,
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

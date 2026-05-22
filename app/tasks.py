from app import db, scheduler
from app.models import Restaurant, Order
from datetime import datetime, timedelta

from flask import has_app_context, current_app

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
        cutoff_time = datetime.now() - timedelta(hours=24)
        print(f"[{datetime.now()}] Checking cleanup... Cutoff: {cutoff_time}")
        
        inactive_restaurants = Restaurant.query.filter(
            Restaurant.is_active == False,
            Restaurant.created_at < cutoff_time
        ).all()
        
        if inactive_restaurants:
            print(f"[{datetime.now()}] Found {len(inactive_restaurants)} inactive restaurants. Deleting...")
            count = 0
            for restaurant in inactive_restaurants:
                try:
                    db.session.delete(restaurant)
                    count += 1
                except Exception as e:
                    print(f"Error deleting restaurant {restaurant.id}: {e}")
            
            try:
                db.session.commit()
                print(f"[{datetime.now()}] Cleanup complete. Deleted {count} records.")
            except Exception as e:
                db.session.rollback()
                print(f"[{datetime.now()}] Commit failed: {e}")
        else:
            print(f"[{datetime.now()}] No inactive accounts found.")

    except Exception as e:
        print(f"CRITICAL ERROR in cleanup task: {e}")


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
        now = datetime.now()
        print(f"[{now}] Checking pending order expiry...")
        
        # Buscar pedidos pendientes que han expirado
        expired_orders = Order.query.filter(
            Order.status == 'pending',
            Order.expires_at.isnot(None),
            Order.expires_at < now
        ).all()
        
        if expired_orders:
            print(f"[{now}] Found {len(expired_orders)} expired pending orders. Expiring...")
            count = 0
            for order in expired_orders:
                try:
                    order.status = 'expired'
                    count += 1
                except Exception as e:
                    print(f"Error expiring order {order.id}: {e}")
            
            try:
                db.session.commit()
                print(f"[{now}] Expiry complete. Expired {count} orders.")
            except Exception as e:
                db.session.rollback()
                print(f"[{now}] Commit failed: {e}")
        else:
            print(f"[{now}] No expired pending orders found.")

    except Exception as e:
        print(f"CRITICAL ERROR in expiry task: {e}")


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

from app import db, scheduler
from app.models import Restaurant
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

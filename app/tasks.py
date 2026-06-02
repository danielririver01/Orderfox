from app import db, scheduler, mail
from app.models import Restaurant, Order, User
from datetime import datetime, timedelta, timezone
from flask import has_app_context, current_app, render_template
from flask_mail import Message

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


def send_subscription_reminders():
    if has_app_context():
        return _perform_reminders()
    else:
        with scheduler.app.app_context():
            return _perform_reminders()

def _perform_reminders():
    PLAN_PRICES = {
        'emprendedor': '30.000',
        'crecimiento': '40.000',
        'elite': '50.000'
    }
    REMINDER_DAYS = {5, 2, 1}

    try:
        now = datetime.now(timezone.utc)
        restaurants = Restaurant.query.filter(
            Restaurant.is_active == True,
            Restaurant.subscription_expires_at.isnot(None)
        ).all()

        sent = 0
        for restaurant in restaurants:
            expires_at = restaurant.subscription_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            delta = expires_at - now
            days_remaining = delta.days

            if days_remaining not in REMINDER_DAYS:
                continue

            user = User.query.filter_by(restaurant_id=restaurant.id).first()
            if not user or not user.email:
                continue

            plan_key = restaurant.plan_type
            plan_name = f"Plan {plan_key.capitalize()}" if plan_key != 'trial' else 'Trial'
            plan_price = PLAN_PRICES.get(plan_key, '—')

            if days_remaining == 1:
                title = 'Tu suscripcion vence manana'
                message = f'Tu suscripcion de {restaurant.name} expira manana. Renueva hoy para evitar que tu menu digital deje de recibir pedidos.'
            elif days_remaining <= 2:
                title = 'Tu suscripcion vence en 2 dias'
                message = f'Quedan solo 2 dias para que venza tu suscripcion de {restaurant.name}. Renueva ahora y sigue operando sin interrupciones.'
            else:
                title = 'Tu suscripcion vence pronto'
                message = f'Tu suscripcion de {restaurant.name} vence en {days_remaining} dias. Renueva tu plan para mantener tu menu digital activo.'

            try:
                msg = Message(
                    subject=f'{title} - Velzia',
                    recipients=[user.email]
                )
                msg.html = render_template(
                    'email/subscription_reminder.html',
                    restaurant_name=restaurant.name,
                    title=title,
                    message=message,
                    renew_url=f"{current_app.config.get('BASE_URL', '')}/renew?plan={plan_key}",
                    plan_name=plan_name,
                    plan_price=plan_price
                )
                mail.send(msg)
                sent += 1
            except Exception as e:
                print(f"[{datetime.now()}] Error sending reminder to {user.email}: {e}")

        print(f"[{datetime.now()}] Subscription reminders sent: {sent}")

    except Exception as e:
        print(f"CRITICAL ERROR in subscription reminders: {e}")


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
    
    # Programar recordatorios de suscripción (todos los días a las 9:00 AM)
    if not scheduler.get_job('subscription_reminders'):
        scheduler.add_job(
            id='subscription_reminders',
            func=send_subscription_reminders,
            trigger='cron',
            hour=9,
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

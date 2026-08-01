"""
reminder_service.py — Recordatorios de suscripción próxima a vencer.
Antes lo orquestaba n8n (cron diario); ahora lo corre APScheduler.
"""
from datetime import datetime, timezone

from flask import current_app, render_template

from app.models import Restaurant, User
from app.services.mail_service import send_email

PLAN_PRICES = {
    'emprendedor': '30.000',
    'crecimiento': '40.000',
    'elite': '50.000',
}
REMINDER_DAYS = {5, 2, 1}


def _build_reminder(restaurant, user, days_remaining) -> dict:
    plan_key = restaurant.plan_type
    plan_name = f"Plan {plan_key.capitalize()}" if plan_key != 'trial' else 'Trial'
    plan_price = PLAN_PRICES.get(plan_key, 'Gratis')

    if days_remaining == 1:
        title = 'Tu suscripcion vence manana'
        message = f'Tu suscripcion de {restaurant.name} expira manana. Renueva hoy para evitar que tu menu digital deje de recibir pedidos.'
    elif days_remaining <= 2:
        title = 'Tu suscripcion vence en 2 dias'
        message = f'Quedan solo 2 dias para que venza tu suscripcion de {restaurant.name}. Renueva ahora y sigue operando sin interrupciones.'
    else:
        title = 'Tu suscripcion vence pronto'
        message = f'Tu suscripcion de {restaurant.name} vence en {days_remaining} dias. Renueva tu plan para mantener tu menu digital activo.'

    base_url = current_app.config.get('BASE_URL', '')
    renew_url = f"{base_url}/renew?plan={plan_key}"
    html = render_template(
        'email/subscription_reminder.html',
        restaurant_name=restaurant.name,
        title=title,
        message=message,
        renew_url=renew_url,
        plan_name=plan_name,
        plan_price=plan_price,
    )

    return {
        'email': user.email,
        'subject': f'{title} - Velzia',
        'html': html,
        'text': message,
        'restaurant_name': restaurant.name,
        'days_remaining': days_remaining,
        'plan_name': plan_name,
        'plan_price': plan_price,
    }


def build_subscription_reminders() -> list:
    """Devuelve la lista de recordatorios pendientes (días 5, 2 y 1)."""
    now = datetime.now(timezone.utc)
    restaurants = Restaurant.query.filter(
        Restaurant.is_active == True,
        Restaurant.subscription_expires_at.isnot(None),
    ).all()

    reminders = []
    for restaurant in restaurants:
        expires_at = restaurant.subscription_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        days_remaining = (expires_at - now).days
        if days_remaining not in REMINDER_DAYS:
            continue

        user = User.query.filter_by(restaurant_id=restaurant.id).first()
        if not user or not user.email:
            continue

        reminders.append(_build_reminder(restaurant, user, days_remaining))

    return reminders


def send_subscription_reminders() -> int:
    """Envía los recordatorios por email. Devuelve cuántos se enviaron."""
    reminders = build_subscription_reminders()
    sent = 0
    for reminder in reminders:
        ok = send_email(
            reminder['email'],
            reminder['subject'],
            reminder['html'],
            text_body=reminder['text'],
        )
        if ok:
            sent += 1
    current_app.logger.info(
        'Recordatorios de suscripción: %d pendientes, %d enviados', len(reminders), sent
    )
    return sent

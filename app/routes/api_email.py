from flask import Blueprint, request, jsonify, current_app, render_template
from app.models import db, Restaurant, User
from datetime import datetime, timezone

api_email_bp = Blueprint('api_email', __name__, url_prefix='/api/email')

PLAN_PRICES = {
    'emprendedor': '30.000',
    'crecimiento': '40.000',
    'elite': '50.000'
}
REMINDER_DAYS = {5, 2, 1}


@api_email_bp.route('/pending-reminders', methods=['POST'])
def pending_reminders():
    api_key = request.headers.get('x-api-key')
    if api_key != current_app.config.get('SERVICE_API_KEY'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        now = datetime.now(timezone.utc)
        restaurants = Restaurant.query.filter(
            Restaurant.is_active == True,
            Restaurant.subscription_expires_at.isnot(None)
        ).all()

        reminders = []
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
                plan_price=plan_price
            )

            reminders.append({
                'email': user.email,
                'subject': f'{title} - Velzia',
                'html': html,
                'restaurant_name': restaurant.name,
                'days_remaining': days_remaining,
                'plan_name': plan_name,
                'plan_price': plan_price,
            })

        return jsonify({'success': True, 'data': reminders, 'count': len(reminders)}), 200

    except Exception as e:
        current_app.logger.error(f"Error in pending-reminders: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

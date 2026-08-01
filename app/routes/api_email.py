from flask import Blueprint, request, jsonify, current_app

from app.services.reminder_service import build_subscription_reminders

api_email_bp = Blueprint('api_email', __name__, url_prefix='/api/email')


@api_email_bp.route('/pending-reminders', methods=['POST'])
def pending_reminders():
    """
    [DEPRECADO] Devuelve la lista de recordatorios de suscripción pendientes.
    El envío ahora lo hace APScheduler (app/tasks.py -> reminder_service).
    Se mantiene por compatibilidad con flujos externos.
    """
    api_key = request.headers.get('x-api-key')
    if api_key != current_app.config.get('SERVICE_API_KEY'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        reminders = build_subscription_reminders()
        return jsonify({'success': True, 'data': reminders, 'count': len(reminders)}), 200

    except Exception as e:
        current_app.logger.error(f"Error in pending-reminders: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

"""
API de reservas (v1.5, feature/reservas).

Dos superficies:
- Público (menú digital, sin auth): check de disponibilidad + crear reserva.
  Protegido con ReservationRateLimiter (mismo espíritu que pedidos: 3/min,
  ban 10 min). CSRF exento en /api/* vía before_request global.
- Restaurante (JWT del dashboard): listar, confirmar, rechazar, completar,
  no_show, calendario del día y settings.

Respuestas: {"success": bool, "message": ..., "data": {...}} (convención del
proyecto). Errores de dominio via ReservationServiceError → código + status.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.models import Restaurant
from app.services import reservation_service as rs
from app.services.notification_service import (
    notify_new_reservation,
    notify_reservation_confirmed,
    notify_reservation_rejected,
)
from app.services.reservation_service import ReservationServiceError
from app.utils.auth import require_active, require_auth
from app.utils.jwt_auth import get_current_restaurant_jwt
from app.utils.rate_limiter import ReservationRateLimiter
from app.utils.timezone import COLOMBIA_TZ

api_reservations_bp = Blueprint('api_reservations', __name__, url_prefix='/api/reservations')


def _error_response(exc: ReservationServiceError):
    return jsonify({'success': False, 'error_code': exc.code, 'error': exc.message}), exc.http_status


def _client_ip():
    return (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or 'unknown')


def _restaurant_by_slug_or_404(slug):
    restaurant = Restaurant.query.filter_by(slug=slug).first()
    if restaurant is None:
        return None, (jsonify({'success': False, 'error_code': 'NOT_FOUND',
                               'error': 'Restaurante no encontrado'}), 404)
    return restaurant, None


# ══ Público (menú digital) ═══════════════════════════════════════════════

@api_reservations_bp.route('/<string:slug>/check', methods=['POST'])
def check_availability(slug):
    """Verifica disponibilidad sin crear la reserva (input asistido del form)."""
    restaurant, err = _restaurant_by_slug_or_404(slug)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        fecha = rs.parse_date(data.get('fecha'))
        hora = rs.parse_time(data.get('hora'))
        party_size = int(data.get('personas', 0))
        if not 1 <= party_size <= rs.MAX_PARTY_SIZE:
            raise ValueError
    except (ValueError, TypeError, ReservationServiceError):
        return jsonify({'success': False, 'error_code': 'VALIDATION_ERROR',
                        'error': 'Fecha, hora y personas son requeridos (personas >= 1)'}), 400

    blocked, _, _ = ReservationRateLimiter.should_block_request(restaurant.id, _client_ip())
    if blocked:
        return jsonify({'success': False, 'error_code': 'RATE_LIMITED',
                        'error': 'Demasiadas consultas. Espera unos minutos.'}), 429

    table, _settings = rs.check_availability(restaurant.id, fecha, hora, party_size)
    return jsonify({'success': True, 'data': {'available': table is not None}})


@api_reservations_bp.route('/<string:slug>', methods=['POST'])
def create_reservation(slug):
    """Crea una solicitud de reserva (estado 'pending') para el restaurante."""
    restaurant, err = _restaurant_by_slug_or_404(slug)
    if err:
        return err

    client_ip = _client_ip()
    blocked, message, _wait = ReservationRateLimiter.should_block_request(restaurant.id, client_ip)
    if blocked:
        return jsonify({'success': False, 'error_code': 'RATE_LIMITED', 'error': message}), 429

    data = request.get_json(silent=True) or {}
    try:
        reservation = rs.create_reservation(
            restaurant.id,
            fecha=data.get('fecha'),
            hora=data.get('hora'),
            party_size=data.get('personas'),
            customer_name=data.get('nombre'),
            customer_whatsapp=data.get('whatsapp'),
            customer_note=data.get('nota'),
            ip_address=client_ip,
        )
    except ReservationServiceError as exc:
        return _error_response(exc)

    notify_new_reservation(reservation)
    return jsonify({
        'success': True,
        'message': 'Solicitud enviada. Te confirmaremos por WhatsApp a la brevedad.',
        'data': {'reservation_id': reservation.id, 'status': reservation.status},
    }), 201


# ══ Restaurante (dashboard, JWT) ═════════════════════════════════════════

@api_reservations_bp.route('', methods=['GET'])
@require_auth
@require_active
def list_reservations():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    fecha = request.args.get('fecha')
    estado = request.args.get('estado')
    try:
        fecha_dt = rs.parse_date(fecha) if fecha else None
    except ReservationServiceError as exc:
        return _error_response(exc)
    if estado and estado not in ('pending', 'confirmed', 'rejected', 'completed', 'no_show'):
        return jsonify({'success': False, 'error_code': 'VALIDATION_ERROR',
                        'error': 'Estado inválido'}), 400

    reservations = rs.get_reservations(restaurant.id, fecha=fecha_dt, estado=estado)
    return jsonify({'success': True, 'data': {'reservations': [
        {
            'id': r.id,
            'table_id': r.table_id,
            'table_name': r.table.name if r.table else None,
            'customer_name': r.customer_name,
            'customer_whatsapp': r.customer_whatsapp,
            'customer_note': r.customer_note,
            'fecha': r.reservation_date.strftime('%Y-%m-%d'),
            'hora': r.reservation_time.strftime('%H:%M'),
            'personas': r.party_size,
            'status': r.status,
            'rejection_reason': r.rejection_reason,
            'reminder_sent': r.reminder_sent,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in reservations
    ]}})


@api_reservations_bp.route('/calendar', methods=['GET'])
@require_auth
@require_active
def day_calendar():
    """Vista calendario de ocupación de un día (default: hoy en Colombia)."""
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    fecha = request.args.get('fecha')
    try:
        fecha_dt = rs.parse_date(fecha) if fecha else None
    except ReservationServiceError as exc:
        return _error_response(exc)
    if fecha_dt is None:
        now = datetime.now(COLOMBIA_TZ).replace(tzinfo=None)
        fecha_dt = now.date()

    calendar = rs.get_day_calendar(restaurant.id, fecha_dt)
    settings = calendar['settings']
    return jsonify({'success': True, 'data': {
        'date': calendar['date'],
        'settings': {
            'service_duration_min': settings.service_duration_min,
            'cleanup_buffer_min': settings.cleanup_buffer_min,
        },
        'rows': calendar['rows'],
    }})


@api_reservations_bp.route('/<int:reservation_id>/confirm', methods=['PATCH'])
@require_auth
@require_active
def confirm_reservation(reservation_id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    try:
        res = rs.confirm_reservation(reservation_id, restaurant.id)
    except ReservationServiceError as exc:
        return _error_response(exc)

    notify_reservation_confirmed(res)
    return jsonify({'success': True, 'message': 'Reserva confirmada',
                    'data': {'id': res.id, 'status': res.status}})


@api_reservations_bp.route('/<int:reservation_id>/reject', methods=['PATCH'])
@require_auth
@require_active
def reject_reservation(reservation_id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    data = request.get_json(silent=True) or {}
    try:
        res = rs.reject_reservation(reservation_id, restaurant.id,
                                    motivo=data.get('motivo'))
    except ReservationServiceError as exc:
        return _error_response(exc)

    notify_reservation_rejected(res)
    return jsonify({'success': True, 'message': 'Reserva rechazada',
                    'data': {'id': res.id, 'status': res.status}})


@api_reservations_bp.route('/<int:reservation_id>/complete', methods=['PATCH'])
@require_auth
@require_active
def complete_reservation(reservation_id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    try:
        res = rs.complete_reservation(reservation_id, restaurant.id)
    except ReservationServiceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'message': 'Reserva completada',
                    'data': {'id': res.id, 'status': res.status}})


@api_reservations_bp.route('/<int:reservation_id>/no-show', methods=['PATCH'])
@require_auth
@require_active
def mark_no_show(reservation_id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    try:
        res = rs.mark_no_show(reservation_id, restaurant.id)
    except ReservationServiceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'message': 'Reserva marcada como no_show',
                    'data': {'id': res.id, 'status': res.status}})


@api_reservations_bp.route('/settings', methods=['GET', 'PATCH'])
@require_auth
@require_active
def reservation_settings():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    if request.method == 'PATCH':
        data = request.get_json(silent=True) or {}
        try:
            settings = rs.update_settings(restaurant.id, data)
        except ReservationServiceError as exc:
            return _error_response(exc)
    else:
        settings = rs.get_or_create_settings(restaurant.id)

    return jsonify({'success': True, 'data': {
        'service_duration_min': settings.service_duration_min,
        'cleanup_buffer_min': settings.cleanup_buffer_min,
        'min_notice_hours': settings.min_notice_hours,
        'max_advance_days': settings.max_advance_days,
        'reservations_enabled': settings.reservations_enabled,
        'reminder_enabled': settings.reminder_enabled,
        'reminder_hours_before': settings.reminder_hours_before,
    }})

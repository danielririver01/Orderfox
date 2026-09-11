"""
Rutas web del panel de Reservas (v1.5, feature/reservas).

Blueprint del dashboard: lista/calendario de reservas + configuración.
Solo orquestan (regla del proyecto): reciben request → llaman
ReservationService → renderizan o devuelven response.

Feature-gating: `has_table_qr` también habilita reservas (misma superficie
de mesas). El settings page muestra blur + upsell si el plan no lo incluye,
patrón tables.html (NO bloqueamos la ruta para permitir el upsell visual).
"""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.models import db
from app.services import reservation_service as rs
from app.services.table_service import TableService
from app.utils.auth import require_active, require_auth, require_role_check
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_feature_access
from app.utils.timezone import COLOMBIA_TZ

reservations_bp = Blueprint('reservations', __name__,
                            url_prefix='/dashboard/reservations')


@reservations_bp.before_request
def _require_dashboard_owner():
    """Las reservas se configuran desde el dueño (patrón tables_bp v2.1.1)."""
    return require_role_check('owner')


def _has_reservations_access(restaurant):
    return check_feature_access(restaurant, 'has_table_qr')


@reservations_bp.route('/')
@require_auth
@require_active
def index():
    """Lista de reservas con filtros (estado, fecha) + contadores."""
    restaurant = get_current_restaurant()
    has_access = _has_reservations_access(restaurant)

    estado = request.args.get('estado') or None
    fecha = request.args.get('fecha') or None
    if estado and estado not in ('pending', 'confirmed', 'rejected', 'completed', 'no_show'):
        estado = None

    fecha_dt = None
    if fecha:
        try:
            fecha_dt = rs.parse_date(fecha)
        except rs.ReservationServiceError:
            flash('Fecha de filtro inválida', 'error')
            fecha_dt = None

    reservations = rs.get_reservations(restaurant.id, fecha=fecha_dt, estado=estado) \
        if has_access else []
    counts = _reservation_counts(restaurant.id) if has_access else {}

    return render_template('dashboard/reservations/index.html',
                           reservations=reservations,
                           estado=estado or '',
                           fecha=fecha or '',
                           counts=counts,
                           has_reservations_access=has_access)


def _reservation_counts(restaurant_id):
    """Contadores por estado para los tabs del panel."""
    from app.models import Reservation
    counts = {status: 0 for status in ('pending', 'confirmed', 'rejected', 'completed', 'no_show')}
    rows = (Reservation.query.with_entities(Reservation.status, db.func.count(Reservation.id))
            .filter(Reservation.restaurant_id == restaurant_id)
            .group_by(Reservation.status).all())
    for status, total in rows:
        counts[status] = total
    counts['all'] = sum(counts.values())
    return counts


@reservations_bp.route('/calendar')
@require_auth
@require_active
def calendar():
    """Vista calendario de ocupación de un día (default: hoy en Colombia)."""
    restaurant = get_current_restaurant()
    has_access = _has_reservations_access(restaurant)

    fecha = request.args.get('fecha')
    fecha_dt = None
    if fecha:
        try:
            fecha_dt = rs.parse_date(fecha)
        except rs.ReservationServiceError:
            flash('Fecha inválida', 'error')
    if fecha_dt is None:
        fecha_dt = datetime.now(COLOMBIA_TZ).replace(tzinfo=None).date()

    calendar_data = rs.get_day_calendar(restaurant.id, fecha_dt) if has_access else None
    return render_template('dashboard/reservations/calendar.html',
                           calendar=calendar_data,
                           fecha=fecha_dt.strftime('%Y-%m-%d'),
                           has_reservations_access=has_access)


@reservations_bp.route('/settings', methods=['GET', 'POST'])
@require_auth
@require_active
def settings():
    """Configuración de reservas + capacidades de mesas."""
    restaurant = get_current_restaurant()
    has_access = _has_reservations_access(restaurant)

    if request.method == 'POST':
        if not has_access:
            abort(403)
        try:
            rs.update_settings(restaurant.id, {
                'service_duration_min': request.form.get('service_duration_min'),
                'cleanup_buffer_min': request.form.get('cleanup_buffer_min'),
                'min_notice_hours': request.form.get('min_notice_hours'),
                'max_advance_days': request.form.get('max_advance_days'),
                'reminder_enabled': request.form.get('reminder_enabled') == 'on',
                'reminder_hours_before': request.form.get('reminder_hours_before'),
                'reservations_enabled': request.form.get('reservations_enabled') == 'on',
            })
            _update_table_capacities_from_form(restaurant.id)
            flash('Configuración guardada', 'success')
        except rs.ReservationServiceError as exc:
            flash(exc.message, 'error')
        return redirect(url_for('reservations.settings'))

    settings_obj = rs.get_or_create_settings(restaurant.id)
    tables = TableService.get_tables(restaurant.id)
    return render_template('dashboard/reservations/settings.html',
                           settings=settings_obj,
                           tables=tables,
                           has_reservations_access=has_access)


def _update_table_capacities_from_form(restaurant_id):
    """Procesa capacity_<table_id> del form de settings. Errores individuales
    no abortan el guardado completo: se reportan y continúan."""
    from app.services.reservation_service import ReservationServiceError  # noqa: F401
    errors = 0
    for key, value in request.form.items():
        if not key.startswith('capacity_'):
            continue
        try:
            table_id = int(key[len('capacity_'):])
        except ValueError:
            continue
        _, error = TableService.update_capacity(restaurant_id, table_id, value)
        if error:
            errors += 1
    if errors:
        flash(f'{errors} capacidad(es) no se pudieron guardar (revisa los valores)',
              'error')

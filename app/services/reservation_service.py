"""
ReservationService — lógica de negocio de Mesas y Reservas (v1.5).

Regla de oro de la disponibilidad (matemática, sin doble booking):

    inicio_reserva = fecha + hora (hora local Colombia)
    fin_bloqueo    = inicio + service_duration_min + cleanup_buffer_min

Una mesa está ocupada para un slot nuevo si existe una reserva en estado
bloqueante ('pending' o 'confirmed') cuya ventana [inicio, fin_bloqueo)
se cruza con la ventana del slot pedido.

- Las reservas 'pending' TAMBIÉN bloquean: si solo bloquearan las
  confirmadas, dos solicitudes pendientes sobre la misma mesa serían
  dobles (la confirmación de ambas crearía el conflicto).
- La duración/config se toma SIEMPRE de ReservationSettings actual del
  restaurante (config única por restaurante; cambiar la config a mitad de
  día es un caso aceptado — el dueño ve el calendario y puede reacomodar).
- Mesas candidatas: is_active=True y capacity >= personas (capacity NULL
  se trata como DEFAULT_CAPACITY). Se elige el "best fit": la de menor
  capacidad que cumple, para no quemar mesas grandes con grupos pequeños.

Zona horaria: las reservas viven en hora local Colombia (ver
app/models/reservations.py — una reserva de 8pm es 8pm en Bogotá).
"""
from datetime import datetime, timedelta

from flask import current_app

from app.models import Reservation, ReservationSettings, Table, db
from app.utils.timezone import COLOMBIA_TZ

# Defaults (sincronizados con los server_default de la migración)
DEFAULT_SERVICE_DURATION_MIN = 90
DEFAULT_CLEANUP_BUFFER_MIN = 15
DEFAULT_MIN_NOTICE_HOURS = 2
DEFAULT_MAX_ADVANCE_DAYS = 30
DEFAULT_CAPACITY = 4

# Estados que bloquean una mesa. 'completed', 'no_show' y 'rejected' liberan.
BLOCKING_STATUSES = ('pending', 'confirmed')

# Límites de saneamiento de la config (evitan configs matemáticamente absurdas)
SERVICE_DURATION_RANGE = (30, 300)   # minutos
CLEANUP_BUFFER_RANGE = (0, 60)       # minutos
MIN_NOTICE_RANGE = (0, 72)           # horas
MAX_ADVANCE_RANGE = (1, 365)         # días
REMINDER_HOURS_RANGE = (1, 24)       # horas

MAX_PARTY_SIZE = 100                 # saneamiento duro del input público


class ReservationServiceError(Exception):
    """Error de dominio de reservas con código y status HTTP asociado."""

    def __init__(self, message, code='VALIDATION_ERROR', http_status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


# ── Helpers de tiempo ─────────────────────────────────────────────────────

def _now_colombia_naive():
    """Ahora en hora Colombia, naive (mismo universo que fecha+hora de reserva)."""
    return datetime.now(COLOMBIA_TZ).replace(tzinfo=None)


def parse_date(value):
    """'YYYY-MM-DD' → date. Lanza ReservationServiceError si es inválido."""
    try:
        # naive a propósito: las reservas viven en hora Colombia (ver módulo)
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()  # noqa: DTZ007
    except (ValueError, TypeError):
        raise ReservationServiceError('Fecha inválida. Formato esperado: YYYY-MM-DD')


def parse_time(value):
    """'HH:MM' o 'HH:MM:SS' → time. Lanza ReservationServiceError si es inválido."""
    raw = str(value).strip()
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(raw, fmt).time()  # noqa: DTZ007
        except ValueError:
            continue
    raise ReservationServiceError('Hora inválida. Formato esperado: HH:MM (24h)')


def _reservation_start(reservation_date, reservation_time):
    return datetime.combine(reservation_date, reservation_time)


def _block_end(start, settings):
    """Fin del bloqueo de una reserva: inicio + duración + buffer."""
    return start + timedelta(
        minutes=settings.service_duration_min + settings.cleanup_buffer_min)


# ── Configuración ─────────────────────────────────────────────────────────

def get_or_create_settings(restaurant_id):
    """Devuelve la config del restaurante, creándola con defaults si no existe."""
    settings = ReservationSettings.query.filter_by(restaurant_id=restaurant_id).first()
    if settings is None:
        settings = ReservationSettings(restaurant_id=restaurant_id)
        db.session.add(settings)
        db.session.commit()
    return settings


def update_settings(restaurant_id, data):
    """Actualiza la config con saneamiento. Devuelve la config actualizada."""
    settings = get_or_create_settings(restaurant_id)

    def _int_range(field, value, rng, label):
        try:
            num = int(value)
        except (TypeError, ValueError):
            raise ReservationServiceError(f'{label} debe ser un número')
        low, high = rng
        if not low <= num <= high:
            raise ReservationServiceError(
                f'{label} debe estar entre {low} y {high}')
        return num

    if 'service_duration_min' in data:
        settings.service_duration_min = _int_range(
            'service_duration_min', data['service_duration_min'],
            SERVICE_DURATION_RANGE, 'La duración del servicio')
    if 'cleanup_buffer_min' in data:
        settings.cleanup_buffer_min = _int_range(
            'cleanup_buffer_min', data['cleanup_buffer_min'],
            CLEANUP_BUFFER_RANGE, 'El buffer de limpieza')
    if 'min_notice_hours' in data:
        settings.min_notice_hours = _int_range(
            'min_notice_hours', data['min_notice_hours'],
            MIN_NOTICE_RANGE, 'La anticipación mínima')
    if 'max_advance_days' in data:
        settings.max_advance_days = _int_range(
            'max_advance_days', data['max_advance_days'],
            MAX_ADVANCE_RANGE, 'La anticipación máxima')
    if 'reminder_hours_before' in data:
        settings.reminder_hours_before = _int_range(
            'reminder_hours_before', data['reminder_hours_before'],
            REMINDER_HOURS_RANGE, 'El recordatorio')
    for flag in ('reservations_enabled', 'reminder_enabled'):
        if flag in data:
            settings.__setattr__(flag, bool(data[flag]))

    db.session.commit()
    return settings


# ── Disponibilidad ────────────────────────────────────────────────────────

def _candidate_tables(restaurant_id, party_size):
    """Mesas activas con capacidad suficiente, best-fit primero."""
    tables = Table.query.filter_by(restaurant_id=restaurant_id, is_active=True).all()
    fitting = [t for t in tables if (t.capacity or DEFAULT_CAPACITY) >= party_size]
    return sorted(fitting, key=lambda t: t.capacity or DEFAULT_CAPACITY)


def _table_is_free(table, start, end, blocking_reservations, settings):
    """True si ninguna reserva bloqueante de la mesa se cruza con [start, end)."""
    for res in blocking_reservations:
        if res.table_id != table.id:
            continue
        existing_start = _reservation_start(res.reservation_date, res.reservation_time)
        existing_end = _block_end(existing_start, settings)
        # Overlap de intervalos semi-abiertos: [a,b) ∩ [c,d) ≠ ∅
        if existing_start < end and start < existing_end:
            return False
    return True


# ── Disponibilidad (continuación) ─────────────────────────────────────

def check_availability(restaurant_id, fecha, hora, party_size):
    """Verifica si hay mesa disponible.

    Returns:
        (table, settings): la mesa best-fit libre y la config. table=None si
        no hay disponibilidad.
    """
    settings = get_or_create_settings(restaurant_id)

    start = _reservation_start(fecha, hora)
    end = _block_end(start, settings)

    blocking = Reservation.query.filter(
        Reservation.restaurant_id == restaurant_id,
        Reservation.reservation_date == fecha,
        Reservation.status.in_(BLOCKING_STATUSES),
    ).all()

    for table in _candidate_tables(restaurant_id, party_size):
        if _table_is_free(table, start, end, blocking, settings):
            return table, settings
    return None, settings


# ── Creación (público) ────────────────────────────────────────────────────

def create_reservation(restaurant_id, *, fecha, hora, party_size,
                       customer_name, customer_whatsapp,
                       customer_note=None, ip_address=None):
    """Crea una reserva 'pending' con asignación automática de mesa.

    El auto-rechazo del plan vive aquí: si no hay mesa libre el sistema NO
    crea la reserva (queda matemáticamente imposible el doble booking por
    saturación) — la API responde 409 con el mensaje para el cliente.

    Raises:
        ReservationServiceError: validación (400) o sin disponibilidad (409).
    """
    # 1. Saneamiento de inputs
    if not customer_name or not str(customer_name).strip():
        raise ReservationServiceError('El nombre es requerido')
    customer_name = str(customer_name).strip()[:100]

    whatsapp = str(customer_whatsapp or '').strip()
    clean = whatsapp.replace(' ', '').replace('-', '')
    if not (7 <= len(clean) <= 20) or not all(c.isdigit() or c == '+' for c in clean):
        raise ReservationServiceError('El número de WhatsApp no es válido')

    try:
        party_size = int(party_size)
    except (TypeError, ValueError):
        raise ReservationServiceError('El número de personas debe ser un número')
    if not 1 <= party_size <= MAX_PARTY_SIZE:
        raise ReservationServiceError(
            f'El número de personas debe estar entre 1 y {MAX_PARTY_SIZE}')

    fecha = parse_date(fecha)
    hora = parse_time(hora)
    customer_note = (str(customer_note).strip()[:500]) if customer_note else None

    # 2. Reglas de negocio (config del restaurante)
    settings = get_or_create_settings(restaurant_id)
    if not settings.reservations_enabled:
        raise ReservationServiceError(
            'Este restaurante no está aceptando reservas en este momento',
            code='RESERVATIONS_DISABLED', http_status=409)

    now = _now_colombia_naive()
    if fecha < now.date():
        raise ReservationServiceError('No se puede reservar en una fecha pasada')
    if fecha > now.date() + timedelta(days=settings.max_advance_days):
        raise ReservationServiceError(
            f'Solo se puede reservar con máximo {settings.max_advance_days} días de anticipación')

    start = _reservation_start(fecha, hora)
    if start < now + timedelta(hours=settings.min_notice_hours):
        raise ReservationServiceError(
            f'Las reservas requieren al menos {settings.min_notice_hours} horas de anticipación')

    # 3. Disponibilidad + creación en la misma transacción (ventana de carrera
    # de milisegundos; el dueño ve el calendario y puede reacomodar manualmente).
    table, settings = check_availability(restaurant_id, fecha, hora, party_size)
    if table is None:
        raise ReservationServiceError(
            'No hay mesas disponibles para ese horario. ¿Intentas otra hora?',
            code='NO_AVAILABILITY', http_status=409)

    reservation = Reservation(
        restaurant_id=restaurant_id,
        table_id=table.id,
        customer_name=customer_name,
        customer_whatsapp=clean,
        customer_note=customer_note,
        reservation_date=fecha,
        reservation_time=hora,
        party_size=party_size,
        status='pending',
        ip_address=ip_address,
    )
    db.session.add(reservation)
    db.session.commit()
    return reservation


# ── Transiciones de estado (panel del restaurante) ────────────────────────

def _get_reservation(reservation_id, restaurant_id):
    res = db.session.get(Reservation, reservation_id)
    if res is None or res.restaurant_id != restaurant_id:
        raise ReservationServiceError('Reserva no encontrada',
                                      code='NOT_FOUND', http_status=404)
    return res


def confirm_reservation(reservation_id, restaurant_id):
    """pendiente → confirmada. La mesa ya estaba bloqueada desde la creación."""
    res = _get_reservation(reservation_id, restaurant_id)
    if res.status != 'pending':
        raise ReservationServiceError(
            f'Solo se pueden confirmar reservas pendientes (estado actual: {res.status})')
    res.status = 'confirmed'
    res.confirmed_at = datetime.now(COLOMBIA_TZ).replace(tzinfo=None)
    db.session.commit()
    return res


def reject_reservation(reservation_id, restaurant_id, motivo=None):
    """pendiente o confirmada → rechazada (libera la mesa)."""
    res = _get_reservation(reservation_id, restaurant_id)
    if res.status in ('rejected', 'completed', 'no_show'):
        raise ReservationServiceError(
            f'La reserva ya está en estado {res.status} y no puede rechazarse')
    res.status = 'rejected'
    res.rejection_reason = (str(motivo).strip()[:500]) if motivo else None
    res.rejected_at = datetime.now(COLOMBIA_TZ).replace(tzinfo=None)
    db.session.commit()
    return res


def complete_reservation(reservation_id, restaurant_id):
    """confirmada → completada (el cliente llegó y comió)."""
    res = _get_reservation(reservation_id, restaurant_id)
    if res.status != 'confirmed':
        raise ReservationServiceError(
            f'Solo se pueden completar reservas confirmadas (estado actual: {res.status})')
    res.status = 'completed'
    db.session.commit()
    return res


def mark_no_show(reservation_id, restaurant_id):
    """confirmada → no_show (el cliente no llegó)."""
    res = _get_reservation(reservation_id, restaurant_id)
    if res.status != 'confirmed':
        raise ReservationServiceError(
            f'Solo las reservas confirmadas pueden marcarse no_show (estado actual: {res.status})')
    res.status = 'no_show'
    db.session.commit()
    return res


# ── Consultas ─────────────────────────────────────────────────────────────

def get_reservations(restaurant_id, fecha=None, estado=None):
    """Lista de reservas, más recientes primero, con filtros opcionales."""
    query = Reservation.query.filter_by(restaurant_id=restaurant_id)
    if fecha is not None:
        query = query.filter(Reservation.reservation_date == fecha)
    if estado:
        query = query.filter(Reservation.status == estado)
    return query.order_by(Reservation.reservation_date.desc(),
                          Reservation.reservation_time.desc()).all()


def get_day_calendar(restaurant_id, fecha):
    """Vista calendario del día: bloqueo por mesa.

    Returns:
        dict con settings y lista de filas por mesa:
        {table_id, table_name, capacity, reservations: [...]} — cada reserva
        con start/end (datetime naive Colombia) para pintar la línea de tiempo.
    """
    settings = get_or_create_settings(restaurant_id)
    tables = Table.query.filter_by(restaurant_id=restaurant_id, is_active=True)\
        .order_by(Table.created_at).all()
    day_reservations = Reservation.query.filter(
        Reservation.restaurant_id == restaurant_id,
        Reservation.reservation_date == fecha,
        Reservation.status.in_(BLOCKING_STATUSES),
    ).all()

    rows = []
    for table in tables:
        table_res = []
        for res in day_reservations:
            if res.table_id != table.id:
                continue
            start = _reservation_start(res.reservation_date, res.reservation_time)
            table_res.append({
                'id': res.id,
                'customer_name': res.customer_name,
                'party_size': res.party_size,
                'status': res.status,
                'start': start.strftime('%H:%M'),
                'end': _block_end(start, settings).strftime('%H:%M'),
            })
        rows.append({
            'table_id': table.id,
            'table_name': table.name,
            'capacity': table.capacity or DEFAULT_CAPACITY,
            'reservations': table_res,
        })
    return {'date': fecha.strftime('%Y-%m-%d'), 'settings': settings, 'rows': rows}


# ── QR → reserva (llegada del cliente) ────────────────────────────────────

def link_qr_to_reservation(restaurant_id, table_id, fecha=None):
    """Al escanear el QR de la mesa: ¿hay reserva confirmada para hoy?

    Si existe, la marca 'completed' y devuelve sus datos para el saludo
    ("Bienvenido Carlos, tu mesa está lista"). Si no, devuelve None (menú
    normal sin reserva).
    """
    if fecha is None:
        fecha = _now_colombia_naive().date()
    res = Reservation.query.filter(
        Reservation.restaurant_id == restaurant_id,
        Reservation.table_id == table_id,
        Reservation.reservation_date == fecha,
        Reservation.status == 'confirmed',
    ).first()
    if res is None:
        return None
    res.status = 'completed'
    db.session.commit()
    return res


# ── Recordatorios automáticos (APScheduler) ───────────────────────────────

def send_reservation_reminders():
    """Envía recordatorios ntfy de reservas confirmadas próximas.

    Busca reservas confirmadas que empiezan dentro de la ventana
    reminder_hours_before de su restaurante y a las que aún no se les ha
    enviado recordatorio. Idempotente: marca reminder_sent=True al enviar.
    Se ejecuta cada 30 minutos → ventana máxima de retraso 30 min.
    """
    now = _now_colombia_naive()
    sent = 0
    try:
        pending = Reservation.query.filter(
            Reservation.status == 'confirmed',
            Reservation.reminder_sent.is_(False),
        ).all()
    except Exception:
        current_app.logger.exception('reservations: no se pudo consultar recordatorios')
        return 0

    from app.models import Restaurant
    for res in pending:
        settings = get_or_create_settings(res.restaurant_id)
        if not settings.reminder_enabled:
            continue
        start = _reservation_start(res.reservation_date, res.reservation_time)
        window_start = now
        window_end = now + timedelta(hours=settings.reminder_hours_before)
        if not (window_start <= start <= window_end):
            continue
        restaurant = db.session.get(Restaurant, res.restaurant_id)
        if restaurant is None:
            continue
        try:
            from app.services.notification_service import notify_reservation_reminder
            notify_reservation_reminder(restaurant, res)
            res.reminder_sent = True
            db.session.commit()
            sent += 1
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                f'reservations: error enviando recordatorio de reserva {res.id}')
    return sent

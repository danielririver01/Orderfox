import time
from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, redirect, request, session

from app.models import Table, db
from app.services import reservation_service as rs
from app.services.notification_service import notify_new_order
from app.services.order_service import OrderService, log_event
from app.services.public_menu_service import PublicMenuService
from app.services.reservation_service import ReservationServiceError
from app.utils.rate_limiter import OrderRateLimiter, ReservationRateLimiter

public_bp = Blueprint('public', __name__)

@public_bp.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@public_bp.route('/menu/api/init-checkout', methods=['POST'])
def init_checkout():
    """Registra el inicio del proceso de checkout en la sesión del usuario para anti-bots."""
    session['checkout_start_time'] = time.time()
    return jsonify({'success': True})

@public_bp.route('/menu/<string:slug>')
@public_bp.route('/menu')
def menu(slug=None):
    """
    El menú digital ahora es servido por el frontend Astro (standalone).
    Redirigimos al frontend para no romper los enlaces/QR existentes
    generados desde el dashboard y las mesas.
    """
    if not slug:
        restaurant = PublicMenuService.get_first_active_restaurant()
        if not restaurant:
            abort(404)
        slug = restaurant.slug

    base_url = current_app.config.get('ASTRO_BASE_URL', current_app.config.get('BASE_URL', request.url_root.rstrip('/')))
    target = f"{base_url}/{slug}/"
    if request.query_string:
        target += '?' + request.query_string.decode('utf-8')
    return redirect(target)

# ── Reservas públicas (v1.5, Semana 3) ────────────────────────────────
# Namespace /menu/api/*: mismo origen que el checkout del menú Astro
# (proxy dev + CORS prod), CSRF-exento, rate-limit por IP.

@public_bp.route('/menu/api/reservations/config', methods=['GET'])
def reservations_config():
    """Config pública de reservas del restaurante (para el formulario).
    Acepta ?slug= o ?restaurant_id=. Solo expone lo que el cliente
    necesita: habilitado, anticipación, tamaño máximo de grupo."""
    slug = request.args.get('slug', '')
    if slug:
        restaurant, _err = PublicMenuService.get_restaurant_by_slug(slug)
    else:
        restaurant = PublicMenuService.get_restaurant_by_id(request.args.get('restaurant_id', 0))
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    settings = rs.get_or_create_settings(restaurant.id)
    has_tables = Table.query.filter_by(restaurant_id=restaurant.id, is_active=True).count() > 0
    return jsonify({'success': True, 'data': {
        'enabled': bool(
            settings.reservations_enabled
            and has_tables
            and PublicMenuService.is_ordering_enabled(restaurant)
        ),
        'min_notice_hours': settings.min_notice_hours,
        'max_advance_days': settings.max_advance_days,
        'max_party_size': rs.MAX_PARTY_SIZE,
    }})


@public_bp.route('/menu/api/reservations/check', methods=['POST'])
def reservations_check():
    """Check de disponibilidad sin crear la reserva (input asistido)."""
    data = request.get_json(silent=True) or {}
    restaurant = PublicMenuService.get_restaurant_by_id(data.get('restaurant_id', 0))
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    try:
        fecha = rs.parse_date(data.get('fecha'))
        hora = rs.parse_time(data.get('hora'))
        party_size = int(data.get('personas', 0))
        if not 1 <= party_size <= rs.MAX_PARTY_SIZE:
            raise ValueError
    except (ValueError, TypeError, ReservationServiceError):
        return jsonify({'success': False, 'error': 'Fecha, hora y personas son requeridos'}), 400

    blocked, _, _ = ReservationRateLimiter.should_block_request(restaurant.id, request.remote_addr or 'unknown')
    if blocked:
        return jsonify({'success': False, 'error': 'Demasiadas consultas. Espera unos minutos.'}), 429

    table, _settings = rs.check_availability(restaurant.id, fecha, hora, party_size)
    return jsonify({'success': True, 'data': {'available': table is not None}})


@public_bp.route('/menu/api/reservations', methods=['POST'])
def reservations_create():
    """Crea una solicitud de reserva ('pending') desde el menú digital.
    Mismo anti-spam que pedidos: honeypot + rate limit por IP."""
    data = request.get_json(silent=True) or {}

    # Honeypot (patrón checkout): bots rellenan campos ocultos
    if data.get('user_secondary_email'):
        return jsonify({'success': False, 'error': 'Actividad sospechosa detectada.'}), 403

    restaurant = PublicMenuService.get_restaurant_by_id(data.get('restaurant_id', 0))
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    blocked, message, _wait = ReservationRateLimiter.should_block_request(
        restaurant.id, request.remote_addr or 'unknown')
    if blocked:
        return jsonify({'success': False, 'error': message}), 429

    try:
        reservation = rs.create_reservation(
            restaurant.id,
            fecha=data.get('fecha'),
            hora=data.get('hora'),
            party_size=data.get('personas'),
            customer_name=data.get('nombre'),
            customer_whatsapp=data.get('whatsapp'),
            customer_note=data.get('nota'),
            ip_address=request.remote_addr or 'unknown',
        )
    except ReservationServiceError as exc:
        return jsonify({'success': False,
                        'error_code': exc.code,
                        'error': exc.message}), exc.http_status

    from app.services.notification_service import notify_new_reservation
    notify_new_reservation(reservation)
    return jsonify({
        'success': True,
        'message': 'Solicitud enviada. Te confirmaremos por WhatsApp a la brevedad.',
        'data': {'reservation_id': reservation.id, 'status': reservation.status},
    }), 201


@public_bp.route('/menu/api/reservations/arrival', methods=['POST'])
def reservations_arrival():
    """Conexión QR → reserva (Semana 3): al escanear el QR de la mesa,
    ¿hay reserva confirmada hoy para esa mesa? Si sí, la marca 'completed'
    y devuelve el saludo. Silencioso si no hay reserva (menú normal)."""
    data = request.get_json(silent=True) or {}
    restaurant = PublicMenuService.get_restaurant_by_id(data.get('restaurant_id', 0))
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    table_id = data.get('table_id')
    if not table_id:
        return jsonify({'success': False, 'error': 'table_id requerido'}), 400

    # Validar que la mesa pertenece al restaurante (no filtrar por ID)
    table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).first()
    if not table:
        return jsonify({'success': False, 'error': 'Mesa no encontrada'}), 404

    reservation = rs.link_qr_to_reservation(restaurant.id, table.id)
    if reservation is None:
        return jsonify({'success': True, 'data': {'has_reservation': False}})

    return jsonify({'success': True, 'data': {
        'has_reservation': True,
        'reservation': {
            'customer_name': reservation.customer_name,
            'party_size': reservation.party_size,
            'time': reservation.reservation_time.strftime('%I:%M %p').lstrip('0').lower(),
            'table_name': table.name,
        },
    }})


@public_bp.route('/menu/api/order', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'cart' not in data:
        return jsonify({'success': False, 'error': 'Carrito vacío'}), 400

    # 1. Validación de Honeypot (Anti-Bots)
    if data.get('user_secondary_email'):
        return jsonify({'success': False, 'error': 'Actividad sospechosa detectada.'}), 403

    # 2. Validación de Tiempo (Time-to-Submit)
    start_time = session.get('checkout_start_time', 0)
    if time.time() - start_time < 3.0:
        return jsonify({
            'success': False,
            'error': '¡Uy, vas muy rápido! Tómate un segundo para revisar tus datos.'
        }), 429

    restaurant = PublicMenuService.get_restaurant_by_id(data.get('restaurant_id', 1))
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    if not restaurant.is_open:
        return jsonify({
            'success': False,
            'error': 'Estamos cerrados en este momento. ¡Vuelve pronto!'
        }), 403

    # Validación estricta de suscripción (Backend)
    if not PublicMenuService.is_ordering_enabled(restaurant):
        return jsonify({
            'success': False,
            'error': 'Pedidos temporalmente desactivados.'
        }), 403

    # Expirar pedidos pendientes antiguos
    PublicMenuService.expire_old_pending_orders(restaurant.id, minutes=30)

    client_ip = request.remote_addr

    should_block, error_message, wait_time = OrderRateLimiter.should_block_request(
        restaurant.id, client_ip
    )

    if should_block:
        return jsonify({
            'success': False,
            'error': error_message,
            'retry_after': wait_time
        }), 429

    order_number = OrderService.generate_order_number(restaurant.id)

    notes = data.get('notes', 'Pedido realizado desde el menú digital.')
    customer_name = data.get('customer_name', 'Cliente Web')
    customer_phone = data.get('customer_phone', '')
    city = data.get('city')
    address = data.get('address')

    # Obtener información de la mesa si existe (JSON del frontend Astro o sesión Flask)
    table_id = data.get('table_id') or (session.get('table_id') if session.get('restaurant_id') == restaurant.id else None)
    table_name = None
    if table_id:
        table = Table.query.get(table_id)
        if table and table.restaurant_id == restaurant.id:
            table_name = table.name

    # Construir notas del pedido
    notes = PublicMenuService.build_order_notes(
        customer_phone=customer_phone,
        table_name=table_name,
        city=city,
        address=address,
        notes=notes,
    )

    # Crear el pedido con los items del carrito. Idempotencia v1.5: el
    # frontend genera un UUID por intento; un reintento (respuesta perdida
    # en red) devuelve el pedido original sin crear otro.
    idempotency_key = (data.get('idempotency_key') or '').strip()[:64] or None
    order, validated_items, total_or_error, created = (
        PublicMenuService.create_order_from_cart(
            restaurant=restaurant,
            cart=data['cart'],
            customer_name=customer_name,
            customer_phone=customer_phone,
            notes=notes,
            table_id=table_id,
            ip_address=client_ip,
            order_number=order_number,
            idempotency_key=idempotency_key,
        )
    )

    if order is None:
        return jsonify({
            'success': False,
            'error': total_or_error.get('message', 'Error al crear el pedido.')
        }), 500

    # Traza y notificación solo para pedidos nuevos. En replay el pedido
    # original ya las tuvo: repetirlas duplicaría la cocina y el sonido.
    if created:
        log_event(order.id, 'order_created', actor_role='customer')
    db.session.commit()

    order_id = order.id
    if created:
        notify_new_order(order_id)

    return jsonify({
        'success': True,
        # order.order_number (no la variable pre-generada): en replay el
        # pedido devuelto es el original, cuyo número es anterior.
        'order_number': order.order_number,
        'order_id': order_id,
        'total': total_or_error,
        'items': validated_items,
        'customer_name': customer_name,
        'address_full': f"{address}, {city}" if address and city else None,
        'table_name': order.table.name if order.table else None
    })

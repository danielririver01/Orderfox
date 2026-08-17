"""
routes/cash_register.py — Blueprint del Centro de Caja.

URL base: /cash-register

Módulo con identidad propia (fuera del dashboard), enfocado en responder
"¿Qué pasó con mi dinero?":

- Resumen del periodo por `paid_at` (dinero real en caja).
- Desglose por método de pago, pedidos pagados, pendientes sin pago.
- Cierres de caja persistentes (con validación de solapamiento).

Nota de roles: hoy NO existe sistema de roles en la app (todos los usuarios
son dueños del restaurante). Cualquier usuario logueado del restaurante puede
cerrar caja; `closed_by` se registra para soportar roles en el futuro.
"""

import json

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)

from app.models import User
from app.services.cash_register_copilot import handle_cash_message
from app.services.cash_register_service import (
    RANGE_TYPES,
    CashRegisterService,
    NoSalesError,
)
from app.services.insights import conversation_service as cs
from app.services.insights import prompt_builder
from app.utils.auth import require_active, require_auth, require_role
from app.utils.restaurant import get_current_restaurant

cash_register_bp = Blueprint('cash_register', __name__, url_prefix='/cash-register')


@cash_register_bp.route('/')
@require_auth
@require_active
@require_role('owner', 'cashier')
def index():
    """Página principal del Centro de Caja."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)
    return render_template('dashboard/cash_register.html', restaurant=restaurant)


@cash_register_bp.route('/api/summary')
@require_auth
@require_active
@require_role('owner')
def api_summary():
    """Resumen + desglose por método de un periodo."""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'not found'}), 404

    range_type = request.args.get('range', 'today')
    if range_type not in RANGE_TYPES:
        return jsonify({'success': False, 'error': 'Rango inválido'}), 400

    try:
        start, end = CashRegisterService.resolve_range(
            range_type,
            from_date=request.args.get('from'),
            to_date=request.args.get('to'),
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    summary = CashRegisterService.get_summary(restaurant.id, start, end)
    return jsonify({'success': True, 'data': summary})


@cash_register_bp.route('/api/orders')
@require_auth
@require_active
@require_role('owner')
def api_orders():
    """Pedidos pagados en el periodo (filtro por método + búsqueda)."""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'not found'}), 404

    range_type = request.args.get('range', 'today')
    if range_type not in RANGE_TYPES:
        return jsonify({'success': False, 'error': 'Rango inválido'}), 400

    try:
        start, end = CashRegisterService.resolve_range(
            range_type,
            from_date=request.args.get('from'),
            to_date=request.args.get('to'),
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    method = request.args.get('method') or None
    search = request.args.get('q') or None
    orders = CashRegisterService.get_paid_orders(
        restaurant.id, start, end, method=method, search=search)

    return jsonify({'success': True, 'data': orders})


@cash_register_bp.route('/api/pending')
@require_auth
@require_active
@require_role('owner', 'cashier')
def api_pending():
    """Pedidos activos sin pago (pendientes de cobrar)."""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'not found'}), 404

    pending = CashRegisterService.get_pending(restaurant.id)
    return jsonify({'success': True, 'data': pending})


@cash_register_bp.route('/api/closes')
@require_auth
@require_active
@require_role('owner')
def api_closes():
    """Historial de cierres recientes."""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'not found'}), 404

    closes = CashRegisterService.get_closes(restaurant.id)
    return jsonify({'success': True, 'data': closes})


@cash_register_bp.route('/close', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def close():
    """Crear un cierre de caja para un rango. Responde JSON (fetch del JS)."""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'not found'}), 404

    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    range_type = data.get('range', 'today')
    if range_type not in RANGE_TYPES:
        return jsonify({'success': False, 'error': 'Rango inválido'}), 400

    try:
        start, end = CashRegisterService.resolve_range(
            range_type,
            from_date=data.get('from'),
            to_date=data.get('to'),
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    try:
        closing = CashRegisterService.close_register(
            restaurant.id, user_id, start, end)
    except NoSalesError as e:
        # 400: no hay ventas en el periodo → no se puede cerrar caja.
        return jsonify({'success': False, 'error': str(e)}), 400
    except ValueError as e:
        # 409: solapamiento o duplicado → el frontend recarga el resumen.
        return jsonify({'success': False, 'error': str(e)}), 409

    return jsonify({
        'success': True,
        'data': {'id': closing.id},
    })


@cash_register_bp.route('/close/<int:close_id>/print')
@require_auth
@require_active
@require_role('owner')
def print_close(close_id):
    """Vista imprimible de un cierre."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    closing = CashRegisterService.get_close(restaurant.id, close_id)
    if not closing:
        abort(404)

    return render_template(
        'dashboard/cash_register_print.html',
        closing=closing,
        restaurant=restaurant,
    )


# ── Copilot de Caja ────────────────────────────────────────────────────────
# Flujo de chat separado de /insights: conversaciones con source='cash_register'.
# Requiere suscripción/plan activo para consumir tokens (TokenService).


@cash_register_bp.route('/copilot/conversations', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def copilot_create_conversation():
    """Crea una conversación de Copilot de Caja."""
    user = session.get('user_id')
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    user = User.query.get(user)
    restaurant = get_current_restaurant()
    if not user or not restaurant:
        return jsonify({'success': False, 'error': 'not found'}), 404

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip() or None
    conv = cs.create_conversation(
        user.id, restaurant.id, title=title,
        prompt_version=prompt_builder.PROMPT_VERSION,
        model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
        source='cash_register',
    )
    return jsonify({
        'success': True,
        'data': {
            'id': conv.id,
            'title': conv.title,
            'source': 'cash_register',
        },
    }), 201


@cash_register_bp.route('/copilot/conversations', methods=['GET'])
@require_auth
@require_active
@require_role('owner')
def copilot_list_conversations():
    """Lista las conversaciones de Copilot de Caja del usuario."""
    user = session.get('user_id')
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    user = User.query.get(user)
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    query = request.args.get('q')
    if query and query.strip():
        convs = cs.search_conversations(user.id, query, source='cash_register')
    else:
        convs = cs.list_conversations(user.id, source='cash_register')
    return jsonify({
        'success': True,
        'data': [
            {
                'id': c.id,
                'title': c.title or 'Análisis de caja',
                'analysis_active': c.analysis_active,
                'updated_at': c.updated_at.isoformat() if c.updated_at else None,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            }
            for c in convs
        ],
    })


@cash_register_bp.route('/copilot/conversations/<int:cid>', methods=['GET'])
@require_auth
@require_active
@require_role('owner')
def copilot_get_conversation(cid):
    """Devuelve una conversación de Copilot de Caja con su historial de mensajes."""
    user = session.get('user_id')
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    user = User.query.get(user)
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    conv = cs.get_conversation(cid, user.id)
    if not conv or conv.source != 'cash_register':
        return jsonify({'success': False, 'error': 'not found'}), 404

    messages = cs.get_messages(cid)
    return jsonify({
        'success': True,
        'data': {
            'id': conv.id,
            'title': conv.title or 'Análisis de caja',
            'source': conv.source,
            'analysis_active': conv.analysis_active,
            'messages': [
                {
                    'id': m.id,
                    'role': m.role,
                    'content': m.content,
                    'metadata': json.loads(m.metadata_json) if m.metadata_json else None,
                    'created_at': m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        },
    })


@cash_register_bp.route('/copilot/conversations/<int:cid>/messages', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def copilot_send_message(cid):
    """Envía un mensaje al Copilot de Caja y obtiene su respuesta."""
    user = session.get('user_id')
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    user = User.query.get(user)
    restaurant = get_current_restaurant()
    if not user or not restaurant:
        return jsonify({'success': False, 'error': 'not found'}), 404

    conv = cs.get_conversation(cid, user.id)
    if not conv or conv.source != 'cash_register':
        return jsonify({'success': False, 'error': 'not found'}), 404

    data = request.get_json(silent=True) or {}
    period = data.get('period') or {}
    content = data.get('content') or ''
    return handle_cash_message(restaurant, user, conv, period, content)

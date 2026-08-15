"""
cash_register_copilot.py — Orquestador de Copilot de Caja (Centro de Caja).

Flujo SEPARADO e independiente de Copilot VZ (/insights). Comparte solo la
infraestructura de bajo nivel: LLM (llm_service), persistencia de
conversaciones (conversation_service) y tokens (TokenService).

Diferencias clave con message_handler.py (insights):
  - El contexto se construye con cash_register_service.get_summary() /
    get_paid_orders() / get_pending(): las MISMAS funciones que usa la
    pantalla del Centro de Caja. Garantiza que las cifras que narra el LLM
    sean idénticas a las que el usuario está viendo (base `paid_at`).
  - NO usa data_service, classifier ni context_manager en el MVP (la
    compresión de contexto para caja se implementará en una v2 si hace falta).
  - Prompt propio (CASH_SYSTEM_PROMPT) con identidad de caja.
"""

import re
import time

from flask import current_app, jsonify

from app.services import cash_register_service
from app.services.insights import conversation_service as cs
from app.services.insights import llm_service, prompt_builder
from app.services.insights.helpers import parse_llm_response
from app.services.token_service import TokenService, is_elite_user

RANGE_LABELS = {
    'today': 'Hoy',
    'yesterday': 'Ayer',
    'last_7': 'Últimos 7 días',
    'last_30': 'Últimos 30 días',
    'last_month': 'Mes pasado',
    'this_year': 'Este año',
    'custom': 'Personalizado',
}


def _period_label(period):
    """Etiqueta legible del periodo para el prompt del LLM."""
    rng = (period or {}).get('range', 'today')
    label = RANGE_LABELS.get(rng, 'Personalizado')
    if rng == 'custom':
        frm = period.get('from') or ''
        to = period.get('to') or ''
        if frm and to:
            label = f'{frm} al {to}'
        elif frm:
            label = f'desde {frm}'
    return label


# ── Filtro por método de pago ───────────────────────────────────────────────
# "solo nequi", "en efectivo", "ventas de tarjeta" → restringe el contexto del
# LLM a ese método. Determinista (regex), sin costo de LLM ni de tokens.
_METHOD_TRIGGERS = [
    ('nequi',       re.compile(r'\bnequi\b', re.IGNORECASE)),
    ('cash',        re.compile(r'\befectiv[oa]?\b|\bcash\b|\bcontado\b', re.IGNORECASE)),
    ('bancolombia', re.compile(r'\bbancolombia\b', re.IGNORECASE)),
    ('card',        re.compile(r'\btarjetas?\b|\bcard\b|\bcr[eé]dito\b|\bd[eé]bito\b', re.IGNORECASE)),
]


def extract_payment_methods(text):
    """Detecta TODOS los métodos de pago mencionados en el mensaje.

    Retorna lista de claves internas ('cash' | 'nequi' | 'bancolombia' |
    'card') en orden fijo de triggers y sin duplicados, o [] si no menciona
    ninguno. Ej: 'solo nequi y efectivo' → ['nequi', 'cash'].
    """
    if not text:
        return []
    found = []
    for method, pattern in _METHOD_TRIGGERS:
        if pattern.search(text) and method not in found:
            found.append(method)
    return found


def extract_payment_method(text):
    """Backward-compat: primer método detectado o None."""
    methods = extract_payment_methods(text)
    return methods[0] if methods else None


def _join_labels(labels):
    """Une etiquetas en español: 1 → 'Nequi', 2 → 'Nequi y Efectivo',
    3+ → 'Nequi, Efectivo y Tarjeta'."""
    if len(labels) == 0:
        return ''
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f'{labels[0]} y {labels[1]}'
    return f"{', '.join(labels[:-1])} y {labels[-1]}"


def _methods_filter(methods):
    """Dict {methods, label} para el contexto/meta, o None si no hay filtro."""
    if not methods:
        return None
    labels = [cash_register_service.METHOD_LABELS.get(m, m) for m in methods]
    return {
        'methods': methods,
        'label': _join_labels(labels),
    }


def build_cash_context(restaurant_id, start, end, period_label, methods=None):
    """Arma el contexto JSON que recibe el LLM (misma fuente que la pantalla).

    Contiene:
      - period: etiqueta del rango activo (para que el LLM sepa qué mira).
      - summary: totales + desglose por método (paid_at).
      - paid_orders: últimos pedidos pagados en el rango (detalle).
      - pending: pedidos activos sin cobrar (dinero que aún no entra a caja).
      - filter: método(s) de pago activos, si el usuario pidió segmentar
        ("solo nequi" → summary y paid_orders llegan filtrados a esos métodos).
    """
    summary = cash_register_service.CashRegisterService.get_summary(
        restaurant_id, start, end, method=methods,
    )
    paid_orders = cash_register_service.CashRegisterService.get_paid_orders(
        restaurant_id, start, end, method=methods,
    )
    pending = cash_register_service.CashRegisterService.get_pending(
        restaurant_id,
    )

    context = {
        'period': {'label': period_label},
        'summary': summary,
        'paid_orders': paid_orders[:50],
        'pending': pending[:30],
    }
    filter_info = _methods_filter(methods)
    if filter_info:
        context['filter'] = filter_info
    return context


def handle_cash_message(restaurant, user, conv, period, content):
    """Procesa un mensaje del Centro de Caja y devuelve la respuesta JSON.

    Args:
        restaurant: Restaurante autenticado (dueño).
        user: Usuario autenticado.
        conv: CopilotConversation (source='cash_register').
        period: dict {range, from, to} con el rango activo del Centro de Caja.
        content: texto del mensaje del usuario.
    Returns:
        Flask Response (jsonify) con el mismo contrato de insights.
    """
    content = (content or '').strip()
    if not content:
        return jsonify({'success': False, 'error': 'empty_content'}), 400

    t0 = time.time()

    # Filtro de método(s) de pago explícito: "solo nequi", "nequi y efectivo", ...
    methods = extract_payment_methods(content)

    # 1) Guardar el mensaje del usuario.
    user_msg = cs.add_message(conv.id, 'user', content)

    # 2) Resolver el rango activo del Centro de Caja.
    try:
        start, end = cash_register_service.CashRegisterService.resolve_range(
            period.get('range', 'today'),
            from_date=period.get('from'),
            to_date=period.get('to'),
        )
    except ValueError as e:
        cs.delete_message(user_msg.id)
        return jsonify({'success': False, 'error': str(e)}), 400

    # Título derivado solo cuando el rango es válido (evita conversación
    # titulada sin mensajes si el turno falla después).
    if not conv.title:
        cs.set_title(conv.id, cs.make_title_from_message(content))

    period_label = _period_label(period)

    # 3) Consumir token SOLO en el primer análisis de la conversación o cuando
    #    se agota el tope de seguimientos gratis (bloque nuevo).
    follow_up = conv.analysis_active
    turn_consumed = False

    # El tope de seguimientos no aplica a Elite (conserva su comportamiento
    # actual de follow-ups gratis).
    if follow_up and not is_elite_user(user):
        follow_up = cs.reserve_follow_up(
            conv.id, current_app.config.get('COPILOT_MAX_FOLLOW_UPS', 4)
        )

    if not follow_up:
        ok, err = TokenService.consume_token(user, source='cash_register')
        if not ok:
            code = (err or {}).get('error_code')
            cs.delete_message(user_msg.id)
            if code == 'SUBSCRIPTION_REQUIRED':
                return jsonify({
                    'success': True,
                    'type': 'subscription_required',
                    'message': (err or {}).get('message'),
                    'message_id': user_msg.id,
                })
            return jsonify({
                'success': True,
                'type': 'no_credits',
                'can_buy': bool(restaurant),
                'message_id': user_msg.id,
                'error_code': code,
            })
        turn_consumed = True
        cs.mark_analysis_active(conv.id)

    # 4) Armar el contexto (misma fuente que la pantalla del Centro de Caja).
    try:
        context = build_cash_context(
            restaurant.id, start, end, period_label, methods=methods,
        )
        history = cs.get_messages(conv.id)
        history_for_llm = [m for m in history if m.id != user_msg.id]
        messages = prompt_builder.build_analysis_messages(
            user_message=content,
            context=context,
            history=history_for_llm,
            restaurant_name=restaurant.name,
            system_prompt=prompt_builder.CASH_SYSTEM_PROMPT,
        )
        raw = llm_service.chat(
            messages, source='cash_register', conversation_id=conv.id,
            restaurant_id=restaurant.id,
        )
    except llm_service.LLMServiceError as e:
        if not follow_up:
            cs.clear_analysis_active(conv.id)
        cs.delete_message(user_msg.id)
        return jsonify({
            'success': False,
            'type': 'llm_error',
            'message': str(e),
            'message_id': user_msg.id,
        }), 502
    except Exception as e:
        current_app.logger.error(f"Copilot de caja analysis error: {e}")
        if not follow_up:
            cs.clear_analysis_active(conv.id)
        cs.delete_message(user_msg.id)
        return jsonify({
            'success': False,
            'type': 'error',
            'message': 'Ocurrió un error inesperado analizando tu caja.',
            'message_id': user_msg.id,
        }), 500

    parsed = parse_llm_response(raw)
    execution_ms = int((time.time() - t0) * 1000)

    meta = {
        'type': 'analysis',
        'source': 'cash_register',
        'period': period_label,
        'credits_used': 1 if turn_consumed else 0,
        'model': 'deepseek-v4-flash',
        'execution_ms': execution_ms,
    }
    filter_info = _methods_filter(methods)
    if filter_info:
        meta['filter'] = filter_info

    if parsed.get('title') and not conv.title:
        cs.set_title(conv.id, parsed['title'][:200])

    assistant_msg = cs.add_message(conv.id, 'assistant', parsed['text'], meta)

    return jsonify({
        'success': True,
        'type': 'analysis',
        'content': parsed['text'],
        'chart': parsed['chart'],
        'metadata': meta,
        'message_id': user_msg.id,
        'assistant_message_id': assistant_msg.id,
    })

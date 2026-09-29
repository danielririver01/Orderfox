"""
Helpers para el blueprint insights — funciones reutilizables de request/response.
"""

import json
import re
from flask import current_app as _current_app, jsonify, session, g, request
from app.models import User
from app.services.insights import conversation_service as cs, chart_service, data_service
from app.services.token_service import TokenService


# ── Constantes ──────────────────────────────────────────────────────────────

# Nota amable para restaurantes en Nivel 2 (pocos datos).
LEARNING_NOTE = (
    'Todavía estoy aprendiendo tu negocio. A medida que registres más ventas, '
    'mis análisis serán más precisos.'
)

# Detecta cuando el usuario quiere un cálculo de impacto numérico real.
CALC_IMPACT_RE = re.compile(
    r'impacto|calcula(?:r)? (?:el )?(?:impacto|ticket|ingres|venta|pedido)|'
    r'cu.nto (?:podr|ganar|aumentar|m.s)|proyect',
    re.I,
)

# Respuesta del guard de alcance.
FOREIGN_RESTAURANT_MSG = (
    "Entiendo tu curiosidad 🤝\n\n"
    "Soy **Copilot VZ**, el asistente de **Velzia**, y mi trabajo es ayudarte "
    "a hacer crecer **tu** negocio. No tengo acceso a datos de otros restaurantes, "
    "así que no podría darte información precisa sobre ellos aunque quisiera.\n\n"
    "Pero lo que **sí** puedo hacer es analizar **tus** datos a fondo. "
    "¿Quieres que te muestre algo de tu negocio? Ventas, productos, lo que prefieras."
)


def compensate_failed_turn(user, cid, token_receipt, follow_up_reserved):
    """Deshace los cobros de un turno que no llegó a entregar análisis.

    VLZ-6 (decisión (b) del propietario): si DeepSeek o el pipeline técnico
    falla, el usuario no paga.

    - Si se cobró un crédito, se devuelve al mismo saldo del que salió y
      queda registrada una transacción `refund` para auditoría.
    - Si el turno era un seguimiento gratis, se libera su reserva para que
      el usuario no pierda el seguimiento.

    Nunca lanza: una compensación fallida se registra, pero no puede
    convertir un 502 del LLM en un 500 opaco.
    """
    try:
        if token_receipt:
            _, err = TokenService.refund_token(user, token_receipt)
            if err:
                _current_app.logger.error(
                    f"WALLET: no se pudo devolver el crédito del usuario "
                    f"{getattr(user, 'id', None)}: {err.get('error_code')}"
                )
        elif follow_up_reserved:
            cs.release_follow_up(cid)
    except Exception:
        _current_app.logger.error(
            "Error compensando turno fallido de Copilot", exc_info=True,
        )


# ── Helpers de request ─────────────────────────────────────────────────────


def current_user():
    """Obtiene el usuario autenticado (JWT o sesión web)."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            return User.query.get(user_id)
        except Exception:
            return None
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(user_id)


# ── Parseo de respuesta LLM ─────────────────────────────────────────────────


def parse_llm_response(raw):
    """Intenta parsear JSON {text, chart?, title?}; si falla, texto plano.

    El modelo no siempre devuelve JSON puro: puede anteponer un saludo
    ("Aquí tienes la gráfica:") o encerrar el JSON en ```json ... ```. En
    esos casos extraemos el objeto JSON de forma tolerante para no romper
    la gráfica (mostrándola como texto crudo).
    """
    raw = (raw or '').strip()

    def _try_json(s):
        try:
            s = re.sub(r',\s*([}\]])', r'\1', s)
            data = json.loads(s)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _as_parsed(obj, fallback_text=''):
        return {
            'text': obj.get('text') or fallback_text,
            'chart': obj.get('chart'),
            'title': obj.get('title'),
        }

    # 1) JSON puro (caso ideal).
    obj = _try_json(raw)
    if obj:
        return _as_parsed(obj)

    # 2) Bloque ```json ... ``` en cualquier parte.
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.S)
    if m:
        obj = _try_json(m.group(1))
        if obj:
            text = obj.get('text') or raw.replace(m.group(0), '').strip()
            return _as_parsed(obj, text)

    # 3) Primer objeto JSON {...} embebido en el texto.
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end > start:
        obj = _try_json(raw[start:end + 1])
        if obj:
            text = obj.get('text') or raw[:start].strip()
            return _as_parsed(obj, text)

    return {'text': raw, 'chart': None, 'title': None}


# ── Respuestas directas (sin LLM, sin crédito) ──────────────────────────────


def foreign_restaurant_response(conv, user_msg_id):
    """Respuesta cuando piden datos de un restaurante ajeno."""
    meta = {
        'type': 'scope_guard',
        'credits_used': 0,
        'model': 'guard',
    }
    assistant_msg = cs.add_message(conv.id, 'assistant', FOREIGN_RESTAURANT_MSG, meta)
    return jsonify({
        'success': True,
        'type': 'scope_guard',
        'content': FOREIGN_RESTAURANT_MSG,
        'metadata': meta,
        'suggestions': chart_service.followup_suggestions(None),
        'message_id': user_msg_id,
        'assistant_message_id': assistant_msg.id,
    })


def empty_state_response(conv, kind, window_label=None):
    """Responde con un estado vacío inteligente (sin LLM, sin crédito)."""
    payload = data_service.build_empty_state(kind, window_label=window_label)
    meta = dict(payload)
    meta['type'] = 'empty_state'
    msg = cs.add_message(conv.id, 'assistant', payload['text'], meta)
    return jsonify({
        'success': True,
        'is_empty_state': True,
        'type': 'empty_state',
        'empty_state': payload,
        'message': {
            'id': msg.id,
            'role': 'assistant',
            'content': payload['text'],
            'metadata': meta,
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
        },
    })

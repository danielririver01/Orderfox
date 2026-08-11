"""
routes/insights.py — Blueprint de Copilot VZ.

URL base: /insights  (módulo con identidad propia, fuera del dashboard).

Flujo de un mensaje (POST /insights/api/conversations/<id>/messages):

  Nivel 1 (quick)  → respuesta inmediata, GRATIS, sin LLM.
   Nivel 2 (analysis):
      - si la conversación ya tiene analysis_active → seguimiento GRATIS (LLM con historial).
      - si no, y hay créditos → consume 1 crédito y llama al LLM directamente.
      - si no hay créditos → {type:'no_credits'} (tarjeta elegante, sin consumir).

  Antes de cualquier respuesta, el router evalúa la MADUREZ DE DATOS del
  restaurante (Nivel 0-3). Si no hay datos suficientes (sin catálogo, sin
  ventas, o ventana sin ventas) devuelve un ESTADO VACÍO INTELIGENTE, sin
  llamar a DeepSeek ni consumir crédito. Nunca respondemos "No hay datos."
"""

import json
from datetime import datetime, timezone

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    render_template,
    request,
    url_for,
)

from app.csrf import csrf
from app.models import CopilotBusinessEvent, CopilotConversation, db
from app.services.insights import (
    context_manager,
    data_service,
    event_engine,
    event_templates,
    prompt_builder,
)
from app.services.insights import (
    conversation_service as cs,
)
from app.services.insights.helpers import (
    current_user as _current_user,
)
from app.services.insights.message_handler import handle_post_message
from app.utils.auth import require_auth

insights_bp = Blueprint('insights', __name__, url_prefix='/insights')

@insights_bp.after_request
def _add_context_to_response(response):
    """Inyecta context_usage y context_optimized en toda respuesta JSON 200."""
    if response.is_json and response.status_code == 200:
        try:
            data = response.get_json()
            if isinstance(data, dict):
                data['context_usage'] = getattr(g, 'context_usage', 0)
                if getattr(g, 'context_optimized', False):
                    data['context_optimized'] = True
                response.set_data(json.dumps(data))
                response.content_type = 'application/json'
        except Exception:
            pass
    return response

# ── Página principal ─────────────────────────────────────────────────────────

@insights_bp.route('/', strict_slashes=False)
@require_auth
def index():
    user = _current_user()
    restaurant_name = None
    if user and user.restaurant and user.restaurant.name:
        restaurant_name = user.restaurant.name
    return render_template(
        'dashboard/insights.html',
        restaurant_name=restaurant_name,
    )


# ── API: listar / crear conversaciones ──────────────────────────────────────

@csrf.exempt
@insights_bp.route('/api/conversations', methods=['GET'])
@require_auth
def api_list_conversations():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    convs = cs.list_conversations(user.id)
    return jsonify({
        'success': True,
        'data': [
            {
                'id': c.id,
                'title': c.title or 'Análisis sin título',
                'prompt_version': c.prompt_version,
                'analysis_active': c.analysis_active,
                'pinned': c.pinned,
                'message_count': c.messages.count(),
                'updated_at': c.updated_at.isoformat() if c.updated_at else None,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            }
            for c in convs
        ],
    })


@csrf.exempt
@insights_bp.route('/api/conversations', methods=['POST'])
@require_auth
def api_create_conversation():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip() or None
    conv = cs.create_conversation(
        user.id, user.restaurant_id, title=title,
        prompt_version=prompt_builder.PROMPT_VERSION,
        model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
    )
    stage = data_service.get_data_stage(user.restaurant_id)
    return jsonify({
        'success': True,
        'data': {
            'id': conv.id,
            'title': conv.title,
            'analysis_active': conv.analysis_active,
            'welcome_suggestions': data_service.welcome_suggestions(user.restaurant_id, stage),
        },
    }), 201


@csrf.exempt
@insights_bp.route('/api/conversations/draft', methods=['POST'])
@require_auth
def api_draft_conversation():
    """Devuelve un borrador vacío existente o crea uno nuevo.

    Evita acumular chats vacíos: si el usuario ya tiene un análisis sin
    mensajes, se reutiliza en lugar de crear otro.
    """
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    draft = cs.find_draft(user.id)
    if not draft:
        draft = cs.create_conversation(
            user.id, user.restaurant_id,
            prompt_version=prompt_builder.PROMPT_VERSION,
            model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
        )
    stage = data_service.get_data_stage(user.restaurant_id)
    return jsonify({
        'success': True,
        'data': {
            'id': draft.id,
            'title': draft.title,
            'analysis_active': draft.analysis_active,
            'welcome_suggestions': data_service.welcome_suggestions(user.restaurant_id, stage),
        },
    })


@csrf.exempt
@insights_bp.route('/api/conversations/<int:cid>', methods=['GET'])
@require_auth
def api_get_conversation(cid):
    user = _current_user()
    conv = cs.get_conversation(cid, user.id) if user else None
    if not conv:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    messages = cs.get_messages(cid)
    g.context_usage = 0
    try:
        ctx_meta = context_manager.get_conv_metadata(conv)
        ctx_summary = ctx_meta.get('summary')
        ctx_compressed = ctx_meta.get('compressed', False)
        context_json = json.dumps(data_service.build_context(conv.restaurant_id, days=90), ensure_ascii=False)
        total, baseline = context_manager.estimate_full_prompt_tokens(
            context_json, messages, '', summary=ctx_summary if ctx_compressed else None
        )
        variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
        used = max(0, total - baseline)
        g.context_usage = min(100, int((used / variable) * 100))
    except Exception:
        pass
    data = {
        'id': conv.id,
        'title': conv.title,
        'analysis_active': conv.analysis_active,
        'context_summary': ctx_meta.get('summary'),
        'context_compressed': ctx_meta.get('compressed', False),
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
    }
    if not messages:
        stage = data_service.get_data_stage(conv.restaurant_id)
        data['welcome_suggestions'] = data_service.welcome_suggestions(conv.restaurant_id, stage)
    return jsonify({'success': True, 'data': data})


@csrf.exempt
@insights_bp.route('/api/conversations/<int:cid>', methods=['DELETE'])
@require_auth
def api_delete_conversation(cid):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    ok = cs.delete_conversation(cid, user.id)
    if not ok:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    return jsonify({'success': True})


@csrf.exempt
@insights_bp.route('/api/conversations/<int:cid>', methods=['PUT'])
@require_auth
def api_rename_conversation(cid):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    conv = cs.get_conversation(cid, user.id)
    if not conv:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    cs.set_title(cid, title or None)
    return jsonify({'success': True, 'data': {'id': conv.id, 'title': conv.title}})


@csrf.exempt
@insights_bp.route('/api/conversations/<int:cid>/pin', methods=['PATCH'])
@require_auth
def api_pin_conversation(cid):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    conv = cs.get_conversation(cid, user.id)
    if not conv:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    data = request.get_json(silent=True) or {}
    pinned = data.get('pinned')
    if pinned is None:
        pinned = not conv.pinned
    # Regla de negocio: máximo 3 análisis fijados.
    if pinned and not conv.pinned and cs.count_pinned(user.id) >= cs.MAX_PINNED:
        return jsonify({
            'success': False,
            'error_code': 'PIN_LIMIT',
            'message': 'Ya tienes 3 análisis fijados. Desfija uno para continuar.',
        }), 409
    cs.set_pinned(cid, bool(pinned))
    return jsonify({'success': True, 'data': {'id': conv.id, 'pinned': conv.pinned}})


# ── API: enviar mensaje (flujo núcleo) ───────────────────────────────────────

@csrf.exempt
@insights_bp.route('/api/conversations/<int:cid>/messages', methods=['POST'])
@require_auth
def api_post_message(cid):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    conv = cs.get_conversation(cid, user.id)
    if not conv:
        return jsonify({'success': False, 'error': 'not_found'}), 404

    data = request.get_json(silent=True) or {}
    return handle_post_message(cid, user, conv, data)


@insights_bp.route('/api/onboarding', methods=['GET'])
@csrf.exempt
@require_auth
def api_onboarding():
    """Devuelve la tarjeta de onboarding según la madurez de datos del restaurante.

    Nivel 0 (sin productos)  → guía para crear categoría / producto.
    Nivel 1 (sin ventas)     → guía para registrar una venta de prueba.
    Nivel ≥2                 → sin tarjeta (ya puede analizar).
    """
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    stage = data_service.get_data_stage(user.restaurant_id)
    level = stage['level']
    if level == 0:
        card = data_service.build_empty_state('no_catalog')
    elif level == 1:
        card = data_service.build_empty_state('no_sales_yet')
    else:
        card = None
    return jsonify({'success': True, 'stage': level, 'card': card})


# ── API: BusinessEvents (insights automáticos) ─────────────────────────────

@csrf.exempt
@insights_bp.route('/api/events/pending', methods=['GET'])
@require_auth
def api_pending_event():
    """Retorna el BusinessEvent activo más prioritario, o null."""
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    ev = event_engine.get_pending_event(user.restaurant_id)
    if not ev:
        return jsonify({'success': True, 'event': None})
    return jsonify({
        'success': True,
        'event': {
            'id': ev.id,
            'kind': ev.kind,
            'priority': ev.priority,
            'title': ev.title,
            'preview': ev.preview,
            'created_at': ev.created_at.isoformat() if ev.created_at else None,
        },
    })


@csrf.exempt
@insights_bp.route('/api/events/<int:eid>/consume', methods=['POST'])
@require_auth
def api_consume_event(eid):
    """Abre el evento en Copilot y ejecuta el análisis automáticamente.

    El usuario ya confirmó su intención al pulsar "Analizar" en el dashboard:
    no debe responder un saludo para obtener el análisis. El mensaje template
    queda como contexto y se dispara el pipeline real (handle_post_message)
    con un prompt predeterminado. El evento se marca consumido antes del
    análisis para que, ante un fallo del LLM, la tarjeta no reaparezca.
    """
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    ev = CopilotBusinessEvent.query.get(eid)
    if not ev or ev.restaurant_id != user.restaurant_id:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    if not ev.active:
        return jsonify({'success': False, 'error': 'already_consumed'}), 409

    tpl = event_templates.TEMPLATES.get(ev.template_key)
    if not tpl:
        return jsonify({'success': False, 'error': 'invalid_template'}), 500

    # Armar mensaje desde template
    if ev.template_data:
        data = json.loads(ev.template_data)
        message_text = tpl['message'].format(**data)
    else:
        message_text = tpl['message']

    # Reusar la misma conversación de eventos (no crear una nueva cada vez)
    draft = None
    prev_event_conv = db.session.query(CopilotBusinessEvent.conversation_id).filter(
        CopilotBusinessEvent.restaurant_id == user.restaurant_id,
        CopilotBusinessEvent.conversation_id.isnot(None),
    ).order_by(CopilotBusinessEvent.created_at.desc()).first()
    if prev_event_conv:
        conv = CopilotConversation.query.get(prev_event_conv[0])
        if conv:
            draft = conv
    if not draft:
        draft = cs.create_conversation(
            user.id, user.restaurant_id,
            title='Eventos del negocio',
            prompt_version=prompt_builder.PROMPT_VERSION,
            model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
        )

    # Agregar mensaje template como assistant
    meta = {
        'type': 'business_event',
        'kind': ev.kind,
        'event_id': ev.id,
    }
    assistant_msg = cs.add_message(draft.id, 'assistant', message_text, meta)

    # Vincular evento a la conversación y marcarlo como consumido
    ev.conversation_id = draft.id
    ev.active = False
    ev.consumed_at = datetime.now(timezone.utc)
    db.session.commit()

    # Ejecutar el análisis automáticamente (el usuario ya confirmó al pulsar
    # "Analizar" en el dashboard). Reusa todo el pipeline: clasificación,
    # contexto, DeepSeek, telemetría y cobro de 1 token en el primer análisis.
    auto_prompt = current_app.config.get('EVENT_AUTO_ANALYSIS_PROMPT') or 'Analiza mi negocio'
    try:
        handle_post_message(
            draft.id, user, draft,
            {'content': auto_prompt},
        )
    except Exception:
        current_app.logger.exception(
            'Error generando análisis automático para evento %s', ev.id)

    return jsonify({
        'success': True,
        'conversation_id': draft.id,
        'assistant_message_id': assistant_msg.id,
        'redirect': url_for('insights.index') + '#conv=' + str(draft.id),
    })


@csrf.exempt
@insights_bp.route('/api/events/<int:eid>/dismiss', methods=['POST'])
@require_auth
def api_dismiss_event(eid):
    """Descarta el evento sin abrirlo."""
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    ev = CopilotBusinessEvent.query.get(eid)
    if not ev or ev.restaurant_id != user.restaurant_id:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    if not ev.active:
        return jsonify({'success': False, 'error': 'already_consumed'}), 409
    ev.active = False
    ev.dismissed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'success': True})




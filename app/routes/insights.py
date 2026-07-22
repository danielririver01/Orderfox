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
import re
import time
from datetime import datetime, timezone, timedelta

from flask import (
    Blueprint, render_template, request, jsonify, session, current_app, abort,
    url_for, g,
)
from app.utils.auth import require_auth, require_active
from app.utils.subscription import is_subscription_active
from app.csrf import csrf
from app.models import db, User, Restaurant, CopilotConversation, CopilotBusinessEvent
from app.services.insights import (
    classifier, data_service, conversation_service as cs, prompt_builder, llm_service,
    event_engine, event_templates, context_manager, chart_service,
)
from app.services.token_service import TokenService

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

# Nota amable para restaurantes en Nivel 2 (pocos datos): el análisis es real,
# pero señalamos que mejorará con más historial.
_LEARNING_NOTE = (
    'Todavía estoy aprendiendo tu negocio. A medida que registres más ventas, '
    'mis análisis serán más precisos.'
)



# Detecta cuando el usuario quiere un cálculo de impacto numérico real.
_CALC_IMPACT_RE = re.compile(
    r'impacto|calcula(?:r)? (?:el )?(?:impacto|ticket|ingres|venta|pedido)|'
    r'cu.nto (?:podr|ganar|aumentar|m.s)|proyect',
    re.I,
)

# Respuesta del guard de alcance: el usuario pide datos de un restaurante ajeno.
_FOREIGN_RESTAURANT_MSG = (
    "Entiendo tu curiosidad 🤝\n\n"
    "Soy **Copilot VZ**, el asistente de **Velzia**, y mi trabajo es ayudarte "
    "a hacer crecer **tu** negocio. No tengo acceso a datos de otros restaurantes, "
    "así que no podría darte información precisa sobre ellos aunque quisiera.\n\n"
    "Pero lo que **sí** puedo hacer es analizar **tus** datos a fondo. "
    "¿Quieres que te muestre algo de tu negocio? Ventas, productos, lo que prefieras."
)



def _current_user():
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


def _parse_llm_response(raw):
    """Intenta parsear JSON {text, chart?, title?}; si falla, texto plano.

    El modelo no siempre devuelve JSON puro: puede anteponer un saludo
    ("Aquí tienes la gráfica:") o encerrar el JSON en ```json ... ```. En
    esos casos extraemos el objeto JSON de forma tolerante para no romper
    la gráfica (mostrándola como texto crudo).
    """
    raw = (raw or '').strip()

    def _try_json(s):
        try:
            # Algunos modelos dejan comas finales; las eliminamos.
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
        model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-chat',
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
            model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-chat',
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
    content = (data.get('content') or '').strip()
    message_id = data.get('message_id')
    # Edición / regeneración: reemplaza la cola de la conversación por una
    # nueva respuesta a partir del mensaje indicado (replace_tail).
    replace_tail = bool(data.get('replace_tail', False))

    # En regeneración el contenido se toma del mensaje reutilizado.
    if replace_tail and message_id and not content:
        _existing = cs.safe_get_message(message_id, cid)
        if _existing:
            content = _existing.content

    if not content:
        return jsonify({'success': False, 'error': 'empty_content'}), 400

    t0 = time.time()

    # 1) Mensaje del usuario: reusar el ya guardado (edición / regeneración)
    #    o crear uno nuevo.
    if message_id:
        user_msg = cs.safe_get_message(message_id, cid)
        if not user_msg:
            user_msg = cs.add_message(cid, 'user', content)
        else:
            # Edición de mensaje ya enviado: actualiza su contenido y borra
            # la cola (mensajes posteriores) para generar una rama nueva.
            if replace_tail:
                cs.update_message_content(user_msg.id, content)
                cs.delete_messages_after(cid, user_msg.id)
    else:
        user_msg = cs.add_message(cid, 'user', content)

    # Poner título a la conversación si es el primer mensaje.
    if not conv.title:
        cs.set_title(cid, cs.make_title_from_message(content))

    # ── Gestión de contexto: estimar uso y comprimir si es necesario ──
    g.context_usage = 0
    g.context_optimized = False
    ctx_summary = None
    ctx_compressed = False
    try:
        history_msgs = cs.get_messages(cid)
        ctx_meta = context_manager.get_conv_metadata(conv)
        ctx_summary = ctx_meta.get('summary')
        ctx_compressed = ctx_meta.get('compressed', False)
        context_json = json.dumps(data_service.build_context(conv.restaurant_id, days=90), ensure_ascii=False)
        total_tokens, baseline = context_manager.estimate_full_prompt_tokens(
            context_json, history_msgs, content, summary=ctx_summary if ctx_compressed else None
        )
        # Usage = % de la parte variable (historial) sobre el espacio disponible
        variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
        used = max(0, total_tokens - baseline)
        g.context_usage = min(100, int((used / variable) * 100))

        # Fase 1: ≥80% y no hay resumen → generarlo ahora (1 request ligeramente más lenta)
        if g.context_usage >= 80 and not ctx_summary and not ctx_compressed:
            summary = context_manager.compress_conversation(cid, conv, context_json, content)
            if summary:
                ctx_summary = summary
                g.context_optimized = True
                ctx_compressed = ctx_meta.get('compressed', False)
                total_tokens, baseline = context_manager.estimate_full_prompt_tokens(
                    context_json, history_msgs, content, summary=ctx_summary
                )
                variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
                used = max(0, total_tokens - baseline)
                g.context_usage = min(100, int((used / variable) * 100))

        # Fase 2: ≥85% → marcar como comprimido (el prompt_builder usará resumen + 5 últimos)
        if g.context_usage >= 85 and ctx_summary and not ctx_compressed:
            meta = context_manager.get_conv_metadata(conv)
            meta['compressed'] = True
            context_manager.save_conv_metadata(conv, meta)
            ctx_compressed = True
            g.context_optimized = True
            total_tokens, baseline = context_manager.estimate_full_prompt_tokens(
                context_json, history_msgs, content, summary=ctx_summary
            )
            variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
            used = max(0, total_tokens - baseline)
            g.context_usage = min(100, int((used / variable) * 100))
    except Exception as e:
        current_app.logger.warning(f"Context management error: {e}")

    # 2) Guard de alcance: si pide DATOS de un restaurante AJENO, respondemos
    #    directo sin LLM ni crédito. Es un problema de confianza, no de
    #    seguridad: evita que el clasificador rápido conteste con las ventas
    #    del usuario ante "ventas ayer de McDonald's".
    restaurant = user.restaurant
    restaurant_name = restaurant.name if restaurant else None
    restaurant_slug = restaurant.slug if restaurant else None
    if classifier.is_foreign_restaurant_query(content, restaurant_name, restaurant_slug):
        return _foreign_restaurant_response(conv, user_msg.id)

    # 3) Clasificación híbrida.
    cls = classifier.classify(content)

    # ── Etapa de madurez de datos (Nivel 0-3) ──
    # Si no hay datos suficientes, respondemos con un estado vacío inteligente:
    # sin llamar a DeepSeek y sin consumir crédito.
    stage = data_service.get_data_stage(conv.restaurant_id)
    if stage['level'] == 0:
        return _empty_state_response(conv, 'no_catalog')
    if stage['level'] == 1:
        return _empty_state_response(conv, 'no_sales_yet')

    # ── Nivel 1: consulta rápida (GRATIS, SQL directo) ──
    if cls['level'] == 'quick':
        result = data_service.handle_quick(conv.restaurant_id, cls['intent'])
        # Sin datos en la ventana → estado vacío (Caso 2), no "No hay datos."
        if data_service.is_empty_quick_result(result):
            label = data_service.window_label_from_days(cls['window'])
            return _empty_state_response(conv, 'no_data_window', window_label=label)
        chart = chart_service.chart_for_intent(conv.restaurant_id, cls['intent'], result)
        execution_ms = int((time.time() - t0) * 1000)
        meta = {
            'type': 'quick',
            'intent': cls['intent'],
            'window': cls['window'],
            'credits_used': 0,
            'model': 'sql',
            'execution_ms': execution_ms,
            'suggestions': chart_service.followup_suggestions(cls, stage=stage, restaurant_id=conv.restaurant_id),
        }
        if chart:
            meta['chart'] = chart
        if stage['level'] == 2:
            meta['note'] = _LEARNING_NOTE
        assistant_msg = cs.add_message(cid, 'assistant', result['text'], meta)
        return jsonify({
            'success': True,
            'type': 'quick',
            'content': result['text'],
            'chart': chart,
            'metadata': meta,
            'suggestions': chart_service.followup_suggestions(cls, stage=stage, restaurant_id=conv.restaurant_id),
            'message_id': user_msg.id,
            'assistant_message_id': assistant_msg.id,
        })

    # ── Nivel 2: análisis IA ──
    # Guarda contra "No hay datos." del LLM: si no hay ventas en la ventana,
    # devolvemos un estado vacío bonito (Caso 2/3) sin gastar crédito.
    if not data_service.has_sales(conv.restaurant_id, cls['window']):
        label = data_service.window_label_from_days(cls['window'])
        kind = 'chart_empty' if re.search(r'gr.ffic|chart|visualiz', content.lower()) else 'no_data_window'
        return _empty_state_response(conv, kind, window_label=label)

    follow_up = conv.analysis_active  # ya se pagó en esta conversación

    # Consumir 1 crédito la primera vez (no en seguimientos). Si no hay
    # créditos, interrumpimos el flujo con una tarjeta elegante (sin consumir).
    if not follow_up:
        ok, err = TokenService.consume_token(user)
        if not ok:
            code = (err or {}).get('error_code')
            # Suscripción vencida (tras gracia): créditos congelados.
            if code == 'SUBSCRIPTION_REQUIRED':
                return jsonify({
                    'success': True,
                    'type': 'subscription_required',
                    'message': (err or {}).get('message'),
                    'message_id': user_msg.id,
                })
            # Sin créditos: ¿puede comprar más? (trial/pago activo = sí)
            can_buy = bool(user.restaurant) and is_subscription_active(
                user.restaurant, include_grace_period=False)
            return jsonify({
                'success': True,
                'type': 'no_credits',
                'can_buy': can_buy,
                'message_id': user_msg.id,
                'error_code': code,
            })
        cs.mark_analysis_active(cid)

    # ── Cálculo de impacto (respuesta directa, sin LLM) ──
    # En una conversación ya pagada, si el usuario pide calcular el impacto,
    # respondemos con una PROYECCIÓN REAL basada en sus ventas (no inventada),
    # sin gastar crédito (es seguimiento).
    wants_calc = bool(_CALC_IMPACT_RE.search(content)) and not re.search(
        r'gr.ffic|chart|visualiz', content.lower())
    if follow_up and wants_calc:
        proj = data_service.projection_uplift(conv.restaurant_id)
        chart = {
            'type': 'bar',
            'title': 'Proyección de impacto',
            'labels': ['Actual', 'Con mejora'],
            'datasets': [{'label': 'Ingresos ($)', 'data': [proj['revenue'], proj['projected_revenue']]}],
        }
        execution_ms = int((time.time() - t0) * 1000)
        meta = {
            'type': 'analysis',
            'intent': 'calc_impact',
            'window': cls['window'],
            'credits_used': 0,
            'model': 'sql',
            'execution_ms': execution_ms,
            'chart': chart,
            'suggestions': chart_service.followup_suggestions(cls, stage=stage, restaurant_id=conv.restaurant_id),
        }
        assistant_msg = cs.add_message(cid, 'assistant', proj['text'], meta)
        return jsonify({
            'success': True,
            'type': 'analysis',
            'content': proj['text'],
            'chart': chart,
            'metadata': meta,
            'suggestions': chart_service.followup_suggestions(cls, stage=stage, restaurant_id=conv.restaurant_id),
            'message_id': user_msg.id,
            'assistant_message_id': assistant_msg.id,
        })

    # Construir contexto + llamar al LLM.
    try:
        context = data_service.build_context(conv.restaurant_id, days=90)
        history = cs.get_messages(cid)
        # Excluir el mensaje de usuario recién guardado para no duplicar.
        history_for_llm = [m for m in history if m.id != user_msg.id]
        messages = prompt_builder.build_analysis_messages(
            user_message=content,
            context=context,
            history=history_for_llm,
            restaurant_name=(user.restaurant.name if user.restaurant else None),
            context_summary=ctx_summary,
            compressed=ctx_compressed,
        )
        raw = llm_service.chat(messages)
    except llm_service.LLMServiceError as e:
        return jsonify({
            'success': False,
            'type': 'llm_error',
            'message': str(e),
            'message_id': user_msg.id,
        }), 502
    except Exception as e:  # noqa
        current_app.logger.error(f"Copilot analysis error: {e}")
        return jsonify({
            'success': False,
            'type': 'error',
            'message': 'Ocurrió un error inesperado analizando tu negocio.',
            'message_id': user_msg.id,
        }), 500

    parsed = _parse_llm_response(raw)
    # El modelo a veces corrompe el dataset de la gráfica (p.ej. mete texto de
    # sugerencias dentro de `data`). Lo saneamos antes de guardar/mostrar.
    parsed['chart'] = chart_service.clean_chart(parsed['chart'])
    execution_ms = int((time.time() - t0) * 1000)
    credits_used = 0 if follow_up else 1

    meta = {
        'type': 'analysis',
        'intent': cls['intent'],
        'window': cls['window'],
        'credits_used': credits_used,
        'model': current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-chat',
        'execution_ms': execution_ms,
        'chart': parsed['chart'] if parsed['chart'] else None,
        'suggestions': chart_service.followup_suggestions(cls, stage=stage, restaurant_id=conv.restaurant_id),
    }
    if stage['level'] == 2:
        meta['note'] = _LEARNING_NOTE

    # Título generado por la IA (solo si la conversación aún no tiene).
    if parsed.get('title') and not conv.title:
        cs.set_title(cid, parsed['title'][:200])

    assistant_msg = cs.add_message(cid, 'assistant', parsed['text'], meta)

    return jsonify({
        'success': True,
        'type': 'analysis',
        'content': parsed['text'],
        'chart': parsed['chart'],
        'metadata': meta,
        'suggestions': chart_service.followup_suggestions(cls, stage=stage, restaurant_id=conv.restaurant_id),
        'message_id': user_msg.id,
        'assistant_message_id': assistant_msg.id,
    })


def _foreign_restaurant_response(conv, user_msg_id):
    """Respuesta directa (sin LLM, sin crédito) cuando piden datos de un ajeno."""
    meta = {
        'type': 'scope_guard',
        'credits_used': 0,
        'model': 'guard',
    }
    assistant_msg = cs.add_message(conv.id, 'assistant', _FOREIGN_RESTAURANT_MSG, meta)
    return jsonify({
        'success': True,
        'type': 'scope_guard',
        'content': _FOREIGN_RESTAURANT_MSG,
        'metadata': meta,
        'suggestions': chart_service.followup_suggestions(None),
        'message_id': user_msg_id,
        'assistant_message_id': assistant_msg.id,
    })


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
    """Abre el evento en Copilot: prepara conversación con mensaje template."""
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
            model=current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-chat',
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


def _empty_state_response(conv, kind, window_label=None):
    """Responde con un estado vacío inteligente (sin LLM, sin crédito)."""
    payload = data_service.build_empty_state(kind, window_label=window_label)
    # Usamos el payload pero FORZAMOS type='empty_state'. El payload trae su
    # propia clave 'type' (el kind, p.ej. 'no_data_window') que de lo contrario
    # sobrescribiría la nuestra y rompería la detección en el historial.
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

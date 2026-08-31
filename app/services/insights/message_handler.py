"""
message_handler.py — Lógica de negocio para POST /api/conversations/<cid>/messages.

Extraída de routes/insights.py para mantener las rutas delgadas.
Contiene: gestión de contexto, clasificación, consultas rápidas, análisis IA,
consumo de créditos, respuestas de scope guard y estados vacíos.
"""

import json
import re
import time

from flask import current_app, g, jsonify

from app.models import CopilotConversation
from app.services.achievement_engine import evaluate as eval_achievement
from app.services.insights import (
    chart_service,
    classifier,
    context_manager,
    data_service,
    llm_service,
    prompt_builder,
)
from app.services.insights import (
    conversation_service as cs,
)
from app.services.insights.helpers import (
    CALC_IMPACT_RE as _CALC_IMPACT_RE,
)
from app.services.insights.helpers import (
    LEARNING_NOTE as _LEARNING_NOTE,
)
from app.services.insights.helpers import (
    empty_state_response as _empty_state_response,
)
from app.services.insights.helpers import (
    foreign_restaurant_response as _foreign_restaurant_response,
)
from app.services.insights.helpers import (
    parse_llm_response as _parse_llm_response,
)
from app.services.token_service import TokenService, is_elite_user
from app.utils.subscription import is_subscription_active

# ── Prompt Injection Protection ──────────────────────────────────────────────
MAX_MESSAGE_LENGTH = 2000

INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(previous|all)\s+instructions', re.IGNORECASE),
    re.compile(r'disregard\s+(your|all)\s+(safety|guidelines)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+\w+', re.IGNORECASE),
    re.compile(r'system\s*:\s*', re.IGNORECASE),
    re.compile(r'override\s*:?\s*', re.IGNORECASE),
    re.compile(r'forget\s+(everything|all)', re.IGNORECASE),
    re.compile(r'new\s+instructions\s*:', re.IGNORECASE),
    re.compile(r'act\s+as\s+if', re.IGNORECASE),
    re.compile(r'pretend\s+you\s+are', re.IGNORECASE),
    re.compile(r'you\s+are\s+DAN', re.IGNORECASE),
    re.compile(r'do\s+anything\s+now', re.IGNORECASE),
    re.compile(r'bypass\s+(all\s+)?restrictions', re.IGNORECASE),
    re.compile(r'reveal\s+(your|all)\s+(system|instructions|prompt)', re.IGNORECASE),
    re.compile(r'what\s+(is|are)\s+your\s+(system|instructions)', re.IGNORECASE),
    re.compile(r'output\s+(your|all)\s+(instructions|prompt|system)', re.IGNORECASE),
]


def sanitize_user_message(text: str) -> str:
    """Sanitiza el mensaje del usuario contra prompt injection.

    - Detecta y filtra patrones de inyección conocidos
    - Limita la longitud del mensaje
    - Retorna el texto sanitizado
    """
    if not text:
        return text

    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub('[FILTRADO]', sanitized)

    return sanitized[:MAX_MESSAGE_LENGTH]


def handle_post_message(cid, user, conv, data):
    """Procesa un mensaje de usuario y genera respuesta (rápida o análisis IA).

    Args:
        cid: ID de la conversación.
        user: Usuario autenticado.
        conv: Instancia de CopilotConversation.
        data: Dict del body JSON (content, message_id, replace_tail).

    Returns:
        Flask Response (jsonify).
    """
    content = (data.get('content') or '').strip()
    message_id = data.get('message_id')
    replace_tail = bool(data.get('replace_tail', False))

    # En regeneración el contenido se toma del mensaje reutilizado.
    if replace_tail and message_id and not content:
        _existing = cs.safe_get_message(message_id, cid)
        if _existing:
            content = _existing.content

    if not content:
        return jsonify({'success': False, 'error': 'empty_content'}), 400

    # ── Prompt Injection Protection ──────────────────────────────────────
    content = sanitize_user_message(content)

    t0 = time.time()

    # 1) Mensaje del usuario: reusar el ya guardado o crear uno nuevo.
    if message_id:
        user_msg = cs.safe_get_message(message_id, cid)
        if not user_msg:
            user_msg = cs.add_message(cid, 'user', content)
        else:
            if replace_tail:
                cs.update_message_content(user_msg.id, content)
                cs.delete_messages_after(cid, user_msg.id)
    else:
        user_msg = cs.add_message(cid, 'user', content)

    # Poner título a la conversación si es el primer mensaje.
    if not conv.title:
        cs.set_title(cid, cs.make_title_from_message(content))

    # ── Clasificación híbrida (primero: define el nivel y la ventana de tiempo) ──
    cls = classifier.classify(content)

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
        context_json = json.dumps(
            data_service.build_context(conv.restaurant_id, days=cls['window']),
            ensure_ascii=False,
        )
        total_tokens, baseline = context_manager.estimate_full_prompt_tokens(
            context_json, history_msgs, content,
            summary=ctx_summary if ctx_compressed else None,
        )
        variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
        used = max(0, total_tokens - baseline)
        g.context_usage = min(100, int((used / variable) * 100))

        # Fase 1: ≥80% y no hay resumen → generarlo ahora
        if g.context_usage >= 80 and not ctx_summary and not ctx_compressed:
            summary = context_manager.compress_conversation(
                cid, conv, context_json, content,
            )
            if summary:
                ctx_summary = summary
                g.context_optimized = True
                ctx_compressed = ctx_meta.get('compressed', False)
                total_tokens, baseline = context_manager.estimate_full_prompt_tokens(
                    context_json, history_msgs, content, summary=ctx_summary,
                )
                variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
                used = max(0, total_tokens - baseline)
                g.context_usage = min(100, int((used / variable) * 100))

        # Fase 2: ≥85% → marcar como comprimido
        if g.context_usage >= 85 and ctx_summary and not ctx_compressed:
            meta = context_manager.get_conv_metadata(conv)
            meta['compressed'] = True
            context_manager.save_conv_metadata(conv, meta)
            ctx_compressed = True
            g.context_optimized = True
            total_tokens, baseline = context_manager.estimate_full_prompt_tokens(
                context_json, history_msgs, content, summary=ctx_summary,
            )
            variable = max(1, context_manager.MAX_INPUT_TOKENS - baseline)
            used = max(0, total_tokens - baseline)
            g.context_usage = min(100, int((used / variable) * 100))
    except Exception as e:
        current_app.logger.warning(f"Context management error: {e}")

    # 2) Guard de alcance: si pide DATOS de un restaurante AJENO
    restaurant = user.restaurant
    restaurant_name = restaurant.name if restaurant else None
    restaurant_slug = restaurant.slug if restaurant else None
    if classifier.is_foreign_restaurant_query(content, restaurant_name, restaurant_slug):
        return _foreign_restaurant_response(conv, user_msg.id)

    # ── Etapa de madurez de datos ──
    # Solo se bloquea cuando el mensaje REQUIERE datos del restaurante.
    # Preguntas generales ("¿qué puedes hacer por mí?", consejos, ayuda de
    # configuración) pasan al agente aunque no haya ventas todavía.
    general_assist = classifier.is_general_assistance(content)
    stage = data_service.get_data_stage(conv.restaurant_id)
    if not general_assist:
        if stage['level'] == 0:
            return _empty_state_response(conv, 'no_catalog')
        if stage['level'] == 1:
            return _empty_state_response(conv, 'no_sales_yet')

    # ── Nivel 1: consulta rápida ──
    if cls['level'] == 'quick':
        result = data_service.handle_quick(conv.restaurant_id, cls['intent'])
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
            'suggestions': chart_service.followup_suggestions(
                cls, stage=stage, restaurant_id=conv.restaurant_id,
            ),
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
            'suggestions': chart_service.followup_suggestions(
                cls, stage=stage, restaurant_id=conv.restaurant_id,
            ),
            'message_id': user_msg.id,
            'assistant_message_id': assistant_msg.id,
        })

    # ── Nivel 2: análisis IA ──
    if not general_assist and not data_service.has_sales(conv.restaurant_id, cls['window']):
        label = data_service.window_label_from_days(cls['window'])
        kind = 'chart_empty' if re.search(
            r'gr.ffic|chart|visualiz', content.lower(),
        ) else 'no_data_window'
        return _empty_state_response(conv, kind, window_label=label)

    follow_up = conv.analysis_active
    turn_consumed = False

    # El tope de seguimientos no aplica a Elite (conserva su comportamiento
    # actual de follow-ups gratis). Regenerar/editar (replace_tail) tampoco
    # incrementa el contador: no penaliza al usuario por corregir una pregunta.
    if follow_up and not replace_tail and not is_elite_user(user):
        follow_up = cs.reserve_follow_up(
            cid, current_app.config.get('COPILOT_MAX_FOLLOW_UPS', 4)
        )

    if not follow_up and not replace_tail:
        ok, err = TokenService.consume_token(user, source='copilot_vz')
        if not ok:
            code = (err or {}).get('error_code')
            if code == 'SUBSCRIPTION_REQUIRED':
                return jsonify({
                    'success': True,
                    'type': 'subscription_required',
                    'message': (err or {}).get('message'),
                    'message_id': user_msg.id,
                })
            can_buy = bool(user.restaurant) and is_subscription_active(
                user.restaurant, include_grace_period=False,
            )
            return jsonify({
                'success': True,
                'type': 'no_credits',
                'can_buy': can_buy,
                'message_id': user_msg.id,
                'error_code': code,
            })
        turn_consumed = True
        cs.mark_analysis_active(cid)

    # ── Cálculo de impacto (seguimiento, sin LLM) ──
    wants_calc = bool(_CALC_IMPACT_RE.search(content)) and not re.search(
        r'gr.ffic|chart|visualiz', content.lower(),
    )
    if follow_up and wants_calc:
        proj = data_service.projection_uplift(conv.restaurant_id)
        chart = {
            'type': 'bar',
            'title': 'Proyección de impacto',
            'labels': ['Actual', 'Con mejora'],
            'datasets': [{
                'label': 'Ingresos ($)',
                'data': [proj['revenue'], proj['projected_revenue']],
            }],
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
            'suggestions': chart_service.followup_suggestions(
                cls, stage=stage, restaurant_id=conv.restaurant_id,
            ),
        }
        assistant_msg = cs.add_message(cid, 'assistant', proj['text'], meta)
        return jsonify({
            'success': True,
            'type': 'analysis',
            'content': proj['text'],
            'chart': chart,
            'metadata': meta,
            'suggestions': chart_service.followup_suggestions(
                cls, stage=stage, restaurant_id=conv.restaurant_id,
            ),
            'message_id': user_msg.id,
            'assistant_message_id': assistant_msg.id,
        })

    # ── Llamar al LLM ──
    try:
        context = data_service.build_context(conv.restaurant_id, days=cls['window'])
        history = cs.get_messages(cid)
        history_for_llm = [m for m in history if m.id != user_msg.id]
        # Fase 2: best practices de industria (máx 1 documento, ~800 tokens).
        # Nunca lanza: si la KB falla, el análisis sigue sin guía.
        from app.services.insights.knowledge_selector import select_knowledge
        knowledge = select_knowledge(content, cls.get('intent'))
        messages = prompt_builder.build_analysis_messages(
            user_message=content,
            context=context,
            history=history_for_llm,
            restaurant_name=(user.restaurant.name if user.restaurant else None),
            context_summary=ctx_summary,
            compressed=ctx_compressed,
            knowledge=knowledge,
        )
        raw = llm_service.chat(
            messages, source='insights', conversation_id=cid,
            restaurant_id=conv.restaurant_id,
        )
    except llm_service.LLMServiceError as e:
        return jsonify({
            'success': False,
            'type': 'llm_error',
            'message': str(e),
            'message_id': user_msg.id,
        }), 502
    except Exception as e:
        current_app.logger.error(f"Copilot analysis error: {e}")
        return jsonify({
            'success': False,
            'type': 'error',
            'message': 'Ocurrió un error inesperado analizando tu negocio.',
            'message_id': user_msg.id,
        }), 500

    parsed = _parse_llm_response(raw)
    parsed['chart'] = chart_service.clean_chart(parsed['chart'])
    execution_ms = int((time.time() - t0) * 1000)
    credits_used = 1 if turn_consumed else 0

    meta = {
        'type': 'analysis',
        'intent': cls['intent'],
        'window': cls['window'],
        'credits_used': credits_used,
        'model': current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
        'execution_ms': execution_ms,
        'chart': parsed['chart'] if parsed['chart'] else None,
        'suggestions': chart_service.followup_suggestions(
            cls, stage=stage, restaurant_id=conv.restaurant_id,
        ),
    }
    if stage['level'] == 2:
        meta['note'] = _LEARNING_NOTE

    if parsed.get('title') and not conv.title:
        cs.set_title(cid, parsed['title'][:200])

    assistant_msg = cs.add_message(cid, 'assistant', parsed['text'], meta)

    try:
        total = CopilotConversation.query.filter_by(
            user_id=user.id, analysis_active=True,
        ).count()
        eval_achievement(user.id, 'ai_analysis', {'total_analyses': total})
    except Exception:
        current_app.logger.warning("Error evaluando logros de IA", exc_info=True)

    return jsonify({
        'success': True,
        'type': 'analysis',
        'content': parsed['text'],
        'chart': parsed['chart'],
        'metadata': meta,
        'suggestions': chart_service.followup_suggestions(
            cls, stage=stage, restaurant_id=conv.restaurant_id,
        ),
        'message_id': user_msg.id,
        'assistant_message_id': assistant_msg.id,
    })

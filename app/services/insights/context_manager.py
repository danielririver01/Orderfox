"""
context_manager.py — Gestión de contexto y compresión de conversaciones.

Estima el uso de tokens del prompt completo (contexto JSON + historial +
mensaje actual) y comprime el historial vía LLM cuando se acerca al límite,
para mantener la conversación dentro de la ventana de contexto del modelo.
"""

import json
from datetime import datetime, timezone

from flask import current_app
from app.models import db
from app.services.insights import llm_service
from app.services.insights import conversation_service as cs


# Límite conservador para el input total del LLM (system + contexto JSON +
# historial + mensaje actual). Por debajo de 16K para margen.
MAX_INPUT_TOKENS = 12000
PREPARE_AT = 0.80   # 80% → generar resumen en background
APPLY_AT = 0.85     # 85% → empezar a usar el resumen

# Aproximaciones de tokens (sin dependencias externas).
# Español: ~3.5 chars/token. JSON: ~2 chars/token.
def estimate_tokens(text, is_json=False):
    if not text:
        return 0
    rate = 2.0 if is_json else 3.5
    return max(1, int(len(text) / rate))


def estimate_full_prompt_tokens(context_json, history_msgs, user_msg_text, summary=None):
    """Estima los tokens del prompt completo y la línea base (sin historial).
    Retorna (total, baseline) donde baseline = system + contexto (parte fija).
    """
    baseline = 1000 + estimate_tokens(context_json, is_json=True)
    total = baseline
    if summary:
        total += estimate_tokens(summary) + 50
    for m in history_msgs:
        total += estimate_tokens(m.content or '')
        if hasattr(m, 'metadata_json') and m.metadata_json:
            try:
                meta = json.loads(m.metadata_json)
                if meta.get('chart'):
                    total += estimate_tokens(json.dumps(meta['chart']), is_json=True)
            except (TypeError, ValueError):
                pass
    total += estimate_tokens(user_msg_text)
    return total, baseline


def get_conv_metadata(conv):
    """Retorna el dict de metadata_json de una conversación."""
    if not conv.metadata_json:
        return {}
    try:
        return json.loads(conv.metadata_json) or {}
    except (TypeError, ValueError):
        return {}


def save_conv_metadata(conv, meta):
    """Guarda el dict en metadata_json de la conversación."""
    conv.metadata_json = json.dumps(meta)
    db.session.commit()


def compress_conversation(cid, conv, context_json, user_msg_text):
    """Llama al LLM para resumir la conversación y guarda el resumen.
    No cobra créditos al usuario — es mantenimiento interno del sistema.
    """
    history = cs.get_messages(cid)
    # Excluir el mensaje actual si ya está guardado
    history_for_llm = [m for m in history if m.content != user_msg_text or m.role != 'user']

    if not history_for_llm:
        return None

    # Construir texto completo del historial para resumir
    transcript_lines = []
    for m in history_for_llm:
        prefix = 'Usuario' if m.role == 'user' else 'Asistente'
        transcript_lines.append(f"{prefix}: {m.content}")
    transcript = '\n\n'.join(transcript_lines)

    compression_prompt = f"""Resume la siguiente conversación entre un usuario y un asistente de análisis de negocios.
Conserva decisiones tomadas, objetivos, métricas clave discutidas, productos mencionados, preferencias del usuario y cualquier conclusión o recomendación.
Puedes descartar saludos, despedidas, repeticiones y detalles irrelevantes.

Conversación:
{transcript}

Resumen en español (máximo 300 palabras, en prosa natural, sin viñetas):"""

    try:
        raw = llm_service.chat([{'role': 'user', 'content': compression_prompt}], max_tokens=500)
        summary = raw.strip()

        # Guardar metadata de compresión
        meta = get_conv_metadata(conv)
        msg_count_before = len(history)
        meta['summary'] = summary
        meta['compressed'] = True
        meta['compression_pending'] = False
        meta['compression_count'] = meta.get('compression_count', 0) + 1
        meta['last_compressed_at'] = datetime.now(timezone.utc).isoformat()
        meta['messages_before'] = msg_count_before
        # No borramos mensajes — solo marcamos comprimido. El prompt_builder
        # usará el resumen + últimos 5 mensajes en lugar de todo el historial.
        save_conv_metadata(conv, meta)
        return summary
    except Exception as e:
        current_app.logger.warning(f"Compression failed for conv {cid}: {e}")
        return None

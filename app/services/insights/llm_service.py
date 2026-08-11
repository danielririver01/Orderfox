"""
llm_service.py — Única capa que conoce la API de DeepSeek.

Cambiar de proveedor (OpenAI, Claude, Gemini) es cambiar esta clase,
no el resto de Copilot VZ. Recibe mensajes en formato chat estándar y
devuelve el contenido del asistente como string.

También registra telemetría de costo por llamada (tabla ai_llm_calls)
cuando se le pasa source/conversation_id/restaurant_id: es observabilidad,
nunca afecta el flujo de negocio.
"""

import time

import requests
from flask import current_app

from app import db
from app.models import AILlmCall


class LLMServiceError(Exception):
    pass


def _estimate_tokens(text):
    """Estimación simple de tokens (~4 caracteres por token)."""
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _record_llm_call(source, conversation_id, restaurant_id, model, messages,
                     response_data, content, execution_ms):
    """Inserta una fila en ai_llm_calls. Silencioso: la telemetría nunca rompe."""
    if not restaurant_id:
        return
    try:
        usage = (response_data or {}).get('usage') or {}
        input_tokens = usage.get('prompt_tokens') or _estimate_tokens(
            ''.join((m.get('content') or '') for m in (messages or [])))
        output_tokens = usage.get('completion_tokens') or _estimate_tokens(content)
        row = AILlmCall(
            source=source or 'unknown',
            conversation_id=conversation_id,
            restaurant_id=restaurant_id,
            model=model,
            input_tokens_est=int(input_tokens),
            output_tokens_est=int(output_tokens),
            execution_ms=int(execution_ms),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:
        current_app.logger.warning(f"Telemetría LLM no registrada: {e}")
        db.session.rollback()


def chat(messages, temperature=0.35, max_tokens=2000, source=None,
         conversation_id=None, restaurant_id=None):
    """
    Llama a DeepSeek chat completions.

    Args:
        messages: lista de {'role','content'}.
        temperature, max_tokens: controles de salida.
        source: origen del copilot ('insights' | 'cash_register') para telemetría.
        conversation_id, restaurant_id: contexto para registrar la llamada
            en ai_llm_calls (opcional; sin restaurant_id no se registra).
    Returns:
        str — contenido devuelto por el asistente.
    Raises:
        LLMServiceError si falta la API key o la API falla.
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        raise LLMServiceError(
            "DEEPSEEK_API_KEY no está configurada. Agrégala a las variables de entorno."
        )

    url = current_app.config.get('DEEPSEEK_API_URL') or 'https://api.deepseek.com/v1/chat/completions'
    model = current_app.config.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash'

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': False,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    t0 = time.time()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content']
        _record_llm_call(
            source=source, conversation_id=conversation_id,
            restaurant_id=restaurant_id, model=model,
            messages=messages, response_data=data, content=content,
            execution_ms=(time.time() - t0) * 1000,
        )
        return content
    except requests.exceptions.Timeout:
        raise LLMServiceError("El análisis tardó demasiado. Intenta de nuevo.")
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"DeepSeek API error: {e}")
        raise LLMServiceError("No pude conectar con el servicio de IA. Intenta más tarde.")
    except (KeyError, IndexError, ValueError) as e:
        current_app.logger.error(f"DeepSeek unexpected response: {e}")
        raise LLMServiceError("Respuesta inesperada del servicio de IA.")

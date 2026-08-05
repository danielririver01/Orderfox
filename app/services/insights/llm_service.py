"""
llm_service.py — Única capa que conoce la API de DeepSeek.

Cambiar de proveedor (OpenAI, Claude, Gemini) es cambiar esta clase,
no el resto de Copilot VZ. Recibe mensajes en formato chat estándar y
devuelve el contenido del asistente como string.
"""

import requests
from flask import current_app


class LLMServiceError(Exception):
    pass


def chat(messages, temperature=0.35, max_tokens=2000):
    """
    Llama a DeepSeek chat completions.

    Args:
        messages: lista de {'role','content'}.
        temperature, max_tokens: controles de salida.
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

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']
    except requests.exceptions.Timeout:
        raise LLMServiceError("El análisis tardó demasiado. Intenta de nuevo.")
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"DeepSeek API error: {e}")
        raise LLMServiceError("No pude conectar con el servicio de IA. Intenta más tarde.")
    except (KeyError, IndexError, ValueError) as e:
        current_app.logger.error(f"DeepSeek unexpected response: {e}")
        raise LLMServiceError("Respuesta inesperada del servicio de IA.")

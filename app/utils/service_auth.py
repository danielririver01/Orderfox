"""
service_auth.py — Auth server-to-server unificada (header `x-api-key`).

Reglas (no relajar sin revisión de seguridad):
- SOLO header `x-api-key`. Nunca query string (`?api_key=` queda en
  access logs, historial del navegador, monitoreo y reportes de error).
- Comparación en tiempo constante (`hmac.compare_digest`).
- Fail-closed: si `SERVICE_API_KEY` no está configurada, todo se rechaza
  (un `None != None` con `==` dejaría pasar sin clave).
"""
import hmac
from functools import wraps

from flask import request, jsonify, current_app


def validate_service_key(provided) -> bool:
    """True solo si `provided` iguala a SERVICE_API_KEY (header únicamente)."""
    expected = current_app.config.get('SERVICE_API_KEY')
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(provided), str(expected))


def require_service_key(f):
    """Decorador para endpoints S2S: 401 si falta o es inválida."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not validate_service_key(request.headers.get('x-api-key')):
            return jsonify({'success': False, 'error': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

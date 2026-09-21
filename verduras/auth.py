"""
Auth del módulo Verduras: API key para mutaciones (mismo patrón que core).

Core valida el header `x-api-key` contra SERVICE_API_KEY para
server-to-server (ver app/extensions.py). Este módulo usa el mismo mecanismo
para sus endpoints de escritura; las lecturas son públicas (menú futuro).

Se usa hmac.compare_digest (comparación en tiempo constante) en vez de `==`.
"""
import hmac

from flask import current_app, request


class VerdurasAuthError(PermissionError):
    """API key ausente o inválida."""


def require_service_api_key() -> None:
    """
    Valida el header `x-api-key` contra SERVICE_API_KEY.

    Levanta VerdurasAuthError si falta la key, falta la config o no coincide.
    """
    provided = request.headers.get('x-api-key')
    expected = current_app.config.get('SERVICE_API_KEY')
    if not provided or not expected:
        raise VerdurasAuthError('x-api-key requerido')
    if not hmac.compare_digest(str(provided), str(expected)):
        raise VerdurasAuthError('x-api-key inválido')

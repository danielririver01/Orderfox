import os

from flask import current_app, request, session
from flask_apscheduler import APScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

scheduler = APScheduler()


def exempt_from_limiter():
    """Exime al scanner IA (Server-to-Server) del rate limiting."""
    api_key = request.headers.get('x-api-key')
    valid_api_key = current_app.config.get('SERVICE_API_KEY')
    return bool(api_key and valid_api_key and api_key == valid_api_key)


def default_limits_exempt():
    """A quién NO se aplican los límites GLOBALES (defaults) de Flask-Limiter.

    - El scanner IA (server-to-server con ``x-api-key`` válida).
    - Sesiones iniciadas: el "Pase VIP" (R-08 / VLZ-16). Los defaults están
      pensados para tráfico anónimo; aplicarlos al uso legítimo del dashboard
      lo rompería (200/día no alcanza para trabajar).

    OJO: esto solo cubre los DEFAULTS. Los ``@limiter.limit`` por-ruta (login
    PIN de empleados, rewards/claim) se aplican SIEMPRE, con sesión o sin ella
    — el VIP no exime de los guards específicos. Antes vivía en un
    ``request_filter`` global que eximía de TODO; ver VLZ-16.
    """
    if exempt_from_limiter():
        return True
    return 'user_id' in session


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=os.getenv("RATELIMIT_DEFAULT", "200 per day;50 per hour").split(";"),
    storage_uri=os.getenv("RATELIMIT_STORAGE_URL", "memory://"),
    default_limits_exempt_when=default_limits_exempt,
    # Si Redis (o el storage configurado) se cae, degradar al viejo
    # comportamiento en memoria en vez de tumbar la app con 500s. El precio
    # es el límite N× por worker hasta que vuelva — mejor que la caída.
    in_memory_fallback_enabled=True,
)

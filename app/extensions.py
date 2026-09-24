import os
from flask_apscheduler import APScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import session, request

scheduler = APScheduler()

def get_limit_key():
    # Por usuario cuando hay sesión (dueño o empleado), si no por IP.
    # Nunca exime: solo particiona el bucket para que un usuario no
    # consuma el de otro ni el de su IP.
    if 'user_id' in session:
        return f"user_{session['user_id']}"
    if 'employee_id' in session:
        return f"employee_{session['employee_id']}"
    return get_remote_address()

def exempt_from_limiter():
    """Exime al scanner IA (Server-to-Server) del rate limiting.

    Header `x-api-key` únicamente + tiempo constante (ver
    app/utils/service_auth.py). Import lazy: extensions se carga antes
    que los blueprints y el helper solo depende de flask.
    """
    from app.utils.service_auth import validate_service_key
    return validate_service_key(request.headers.get('x-api-key'))

limiter = Limiter(
    key_func=get_limit_key,
    default_limits=os.getenv("RATELIMIT_DEFAULT", "200 per day;50 per hour").split(";"),
    storage_uri=os.getenv("RATELIMIT_STORAGE_URL", "memory://"),
    default_limits_exempt_when=exempt_from_limiter,
)

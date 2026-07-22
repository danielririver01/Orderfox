import os
from flask_apscheduler import APScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import session, request, current_app

scheduler = APScheduler()

def get_limit_key():
    if 'user_id' in session:
        return f"user_{session['user_id']}"
    return get_remote_address()

def exempt_from_limiter():
    """Exime al scanner IA (Server-to-Server) del rate limiting."""
    api_key = request.headers.get('x-api-key')
    valid_api_key = current_app.config.get('SERVICE_API_KEY')
    if api_key and valid_api_key and api_key == valid_api_key:
        return True
    return False

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=os.getenv("RATELIMIT_DEFAULT", "200 per day;50 per hour").split(";"),
    storage_uri=os.getenv("RATELIMIT_STORAGE_URL", "memory://"),
    default_limits_exempt_when=exempt_from_limiter,
)

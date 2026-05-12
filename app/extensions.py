from flask_mail import Mail
from flask_apscheduler import APScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import session, request, current_app

mail = Mail()
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
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    default_limits_exempt_when=exempt_from_limiter,
)

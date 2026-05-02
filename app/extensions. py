from flask_mail import Mail
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import session

mail = Mail()
scheduler = APScheduler()
csrf = CSRFProtect()

def get_limit_key():
    if 'user_id' in session:
        return f"user_{session['user_id']}"
    return get_remote_address()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

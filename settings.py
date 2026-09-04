import os
import logging
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# App Version
APP_VERSION = '1.4.0'
APP_RELEASE_DATE = '2026-07-15'

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY no está configurada. "
            "Establece SECRET_KEY en el archivo .env o como variable de entorno."
        )
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://root:@localhost/orderfox'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Pool acotado: hosts free-tier (p.ej. max_user_connections=10) se saturan
    # con el default de SQLAlchemy (pool_size=5 + max_overflow=10 por proceso).
    # Las opciones de QueuePool solo aplican a motores con pool (MySQL/Postgres),
    # no a sqlite:// (StaticPool) que usa la suite de tests.
    _is_sqlite = (SQLALCHEMY_DATABASE_URI or '').startswith('sqlite')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
        **(
            {} if _is_sqlite else {
                "pool_size": int(os.environ.get('DB_POOL_SIZE', '2')),
                "max_overflow": int(os.environ.get('DB_MAX_OVERFLOW', '1')),
                "pool_timeout": int(os.environ.get('DB_POOL_TIMEOUT', '30')),
            }
        ),
    }
    
    # Mercado Pago
    MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
    MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY')
    MP_WEBHOOK_SECRET = os.environ.get('MP_WEBHOOK_SECRET')
    
    # Soporte y Globales
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL') or 'soporte@velzia.com'
    SUPPORT_PHONE = os.environ.get('SUPPORT_PHONE') or '+573000000000'
    BASE_URL = os.environ.get('BASE_URL') # URL base para QRs y links de Flask (ngrok o dominio)
    ASTRO_BASE_URL = os.environ.get('ASTRO_BASE_URL') # Origen del frontend Astro (menú público)

    # Configuración de Archivos
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # Clerk Configuration
    CLERK_PUBLISHABLE_KEY = os.environ.get('CLERK_PUBLISHABLE_KEY') or os.environ.get('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY')
    CLERK_SECRET_KEY = os.environ.get('CLERK_SECRET_KEY')
    CLERK_JWT_ISSUER = os.environ.get('CLERK_JWT_ISSUER') or 'https://oriented-tortoise-50.clerk.accounts.dev'
    CLERK_WEBHOOK_SECRET = os.environ.get('CLERK_WEBHOOK_SECRET')

    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # Scanner IA Integration
    # En producción configurar como https://velzia.co/scanner-IA
    SCANNER_IA_URL = os.environ.get('SCANNER_IA_URL') or 'http://localhost:3000'
    SERVICE_API_KEY = os.environ.get('SERVICE_API_KEY')

    # Copilot VZ (DeepSeek AI) Integration
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
    DEEPSEEK_API_URL = os.environ.get('DEEPSEEK_API_URL') or 'https://api.deepseek.com/v1/chat/completions'
    DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash'

    # Copilot VZ — Control de costo por conversación
    # Nº de seguimientos gratis por bloque de análisis (1 token por bloque).
    # Al llegar al tope, el siguiente mensaje consume un token nuevo (bloque nuevo).
    COPILOT_MAX_FOLLOW_UPS = int(os.environ.get('COPILOT_MAX_FOLLOW_UPS', '4'))
    # Máx. mensajes de historial enviados al LLM por llamada (control de tokens).
    # Aplica a TODOS los planes, incluido Elite.
    COPILOT_MAX_HISTORY_MESSAGES = int(os.environ.get('COPILOT_MAX_HISTORY_MESSAGES', '15'))

    # AutoPhoto — Fotos automáticas para productos sin imagen
    UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    AUTOPHOTO_ENABLED = os.environ.get('AUTOPHOTO_ENABLED', 'true').lower() in ('1', 'true', 'yes', 'on')

    # JWT Configuration (Mobile API)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or os.environ.get('SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    # CSRF: disable default check; we run it manually for non-API routes
    WTF_CSRF_CHECK_DEFAULT = False

    # Session cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False  # True en producción con HTTPS

    # Correo (Gmail SMTP) — reemplaza el envío que hacía n8n
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('1', 'true', 'yes', 'on')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME')

    # Sentry (error tracking)
    SENTRY_DSN = os.environ.get('SENTRY_DSN')

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    LOG_FORMAT = os.environ.get('LOG_FORMAT', 'json')

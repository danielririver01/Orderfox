import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# App Version
APP_VERSION = '1.3.0'
APP_RELEASE_DATE = '2026-04-14'

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # ⚠️ Este valor seguro SOLO debe usarse en desarrollo.
        # En producción, configurar SECRET_KEY como variable de entorno.
        SECRET_KEY = 'una-clave-secreta-muy-larga-para-desarrollo-seguro'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://root:@localhost/orderfox'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }
    
    # Mercado Pago
    MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
    MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY')
    
    # Soporte y Globales
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL') or 'soporte@velzia.com'
    SUPPORT_PHONE = os.environ.get('SUPPORT_PHONE') or '+573000000000'
    BASE_URL = os.environ.get('BASE_URL') # URL base para QRs y links (ngrok o dominio)

    # Configuración de Archivos
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # Clerk Configuration
    CLERK_PUBLISHABLE_KEY = os.environ.get('CLERK_PUBLISHABLE_KEY') or os.environ.get('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY')
    CLERK_SECRET_KEY = os.environ.get('CLERK_SECRET_KEY')
    CLERK_JWT_ISSUER = os.environ.get('CLERK_JWT_ISSUER') or 'https://oriented-tortoise-50.clerk.accounts.dev'

    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # Scanner IA Integration
    # En producción configurar como https://velzia.co/scanner-IA
    SCANNER_IA_URL = os.environ.get('SCANNER_IA_URL') or 'http://localhost:3000'
    SERVICE_API_KEY = os.environ.get('SERVICE_API_KEY')

    # JWT Configuration (Mobile API)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or os.environ.get('SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    # CSRF: enable default check; API routes exempted via before_request
    WTF_CSRF_CHECK_DEFAULT = True

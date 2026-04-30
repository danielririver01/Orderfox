import os
from dotenv import load_dotenv

load_dotenv()

# App Version
APP_VERSION = '1.3.0'
APP_RELEASE_DATE = '2026-04-14'

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-para-desarrollo'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://root:@localhost/orderfox'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }
    
    # Mail Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME')
    
    # Mercado Pago
    MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
    MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY')
    
    # Soporte y Globales
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL') or 'soporte@velzia.com'
    SUPPORT_PHONE = os.environ.get('SUPPORT_PHONE') or '+573000000000'
    BASE_URL = os.environ.get('BASE_URL') # URL base para QRs y links (ngrok o dominio)

    # Configuración de Archivos
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

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

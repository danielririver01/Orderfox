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

    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    FACEBOOK_CLIENT_ID = os.environ.get('FACEBOOK_CLIENT_ID')
    FACEBOOK_CLIENT_SECRET = os.environ.get('FACEBOOK_CLIENT_SECRET')

    # Clerk Auth
    CLERK_PUBLISHABLE_KEY = os.environ.get('CLERK_PUBLISHABLE_KEY')
    CLERK_SECRET_KEY = os.environ.get('CLERK_SECRET_KEY')
    CLERK_FRONTEND_API = os.environ.get('CLERK_FRONTEND_API')

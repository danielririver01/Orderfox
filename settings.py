import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        print("WARNING: SECRET_KEY not set in environment. Using default insecure key.")
        SECRET_KEY = 'una_clave_secreta_muy_dificil'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://root:@localhost/ventas_por_wh'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCHEDULER_API_ENABLED = True
    
    # Soporte Técnico
    SUPPORT_PHONE = os.environ.get('TELEPHONE') 
    SUPPORT_EMAIL = os.environ.get('EMAILS') 

    # Configuración de Email (Gmail)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = (os.environ.get('MAIL_SENDER_NAME', 'Velzia'), os.environ.get('MAIL_USERNAME'))

    # Mercado Pago
    MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')

    # Base URL (Tunnels/Production)
    BASE_URL = os.environ.get('BASE_URL') or 'http://localhost:5000'
from flask import Flask
from .models import db, migrate
from flask_mail import Mail

mail = Mail()


def create_app():
    app = Flask(__name__, template_folder='template')
    app.config.from_object('settings.Config')
    db.init_app(app)
    mail.init_app(app)

    #Registramos blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.categories import categories_bp
    from .routes.products import products_bp
    from .routes.orders import orders_bp
    from .routes.public import public_bp
    from .routes.menu import menu_bp

    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(menu_bp)

    migrate.init_app(app, db)
    
    # Inyectar variables de soporte globalmente
    @app.context_processor
    def inject_support_info():
        return {
            'SUPPORT_PHONE': app.config.get('SUPPORT_PHONE'),
            'SUPPORT_EMAIL': app.config.get('SUPPORT_EMAIL')
        }

    @app.after_request
    def add_header(response):
        """
        Inyectar cabeceras para prevenir que el navegador cachee páginas protegidas.
        Esto evita que el botón 'Atrás' funcione después del logout.
        """
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return app

    
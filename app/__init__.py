from flask import Flask
from .models import db, migrate
from flask_mail import Mail
from flask_apscheduler import APScheduler

mail = Mail()
scheduler = APScheduler()


def create_app():
    app = Flask(__name__, template_folder='template')
    app.config.from_object('settings.Config')
    db.init_app(app)
    mail.init_app(app)

    # Inicializar Scheduler
    scheduler.init_app(app)
    scheduler.start()

    from .tasks import init_tasks
    init_tasks(scheduler)

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

    # --- Comandos CLI ---
    @app.cli.command("cleanup-accounts")
    def cleanup_accounts_command():
        """Ejecuta manualmente la limpieza de cuentas inactivas."""
        from .tasks import delete_inactive_accounts
        print("Iniciando limpieza manual...")
        delete_inactive_accounts()
        print("Comando de limpieza finalizado.")

    return app

    
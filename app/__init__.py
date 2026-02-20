import os
from flask import Flask, render_template
from .models import db, migrate
from flask_mail import Mail
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from whitenoise import WhiteNoise

mail = Mail()
scheduler = APScheduler()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


def create_app():
    app = Flask(__name__, 
                template_folder='template',
                static_folder='static',
                static_url_path='/static')
    app.config.from_object('settings.Config')
    db.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Servir archivos estáticos en producción con WhiteNoise
    static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.wsgi_app = WhiteNoise(app.wsgi_app, root=static_folder, prefix='static')

    scheduler.init_app(app)
    scheduler.start()

    from .tasks import init_tasks
    init_tasks(scheduler)

    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.categories import categories_bp
    from .routes.products import products_bp
    from .routes.orders import orders_bp
    from .routes.public import public_bp
    from .routes.menu import menu_bp
    from .routes.tables import tables_bp

    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(tables_bp)

    migrate.init_app(app, db)
    
    @app.before_request
    def block_grace_period_crud():
        from flask import request, flash, redirect, url_for
        from app.utils.restaurant import get_current_restaurant
        from app.utils.subscription import can_perform_crud
        
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if request.endpoint and ('auth.' in request.endpoint or 'payment' in request.endpoint or 'public.' in request.endpoint):
                return
                
            restaurant = get_current_restaurant()
            if restaurant and not can_perform_crud(restaurant):
                flash('Tu suscripción ha vencido. No puedes realizar cambios hasta que renueves tu plan.', 'warning')
                return redirect(request.referrer or url_for('dashboard.index'))



    @app.after_request
    def add_header(response):
        """
        Inyectar cabeceras para prevenir que el navegador cachee páginas protegidas.
        Esto evita que el botón 'Atrás' funcione después del logout.
        No aplicar a archivos estáticos (CSS, JS, imágenes).
        """
        from flask import request
        # Excluir archivos estáticos del no-cache para que WhiteNoise funcione
        if not request.path.startswith('/static'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '-1'
        return response

    # Inyectar variables de soporte y suscripción globalmente
    @app.context_processor
    def inject_global_data():
        from app.utils.restaurant import get_current_restaurant
        from app.utils.subscription import get_subscription_status
        
        data = {
            'SUPPORT_PHONE': app.config.get('SUPPORT_PHONE'),
            'SUPPORT_EMAIL': app.config.get('SUPPORT_EMAIL'),
            'sub_status': None
        }
        
        restaurant = get_current_restaurant()
        if restaurant:
            data['sub_status'] = get_subscription_status(restaurant)
            
        return data

    # --- Comandos CLI ---
    @app.cli.command("cleanup-accounts")
    def cleanup_accounts_command():
        """Ejecuta manualmente la limpieza de cuentas inactivas."""
        from .tasks import delete_inactive_accounts
        print("Iniciando limpieza manual...")
        delete_inactive_accounts()
        print("Comando de limpieza finalizado.")

    # Manejadores de errores personalizados
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    return app

    
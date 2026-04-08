import os
from flask import Flask, render_template, session
from .models import db, migrate,User
from flask_mail import Mail
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from whitenoise import WhiteNoise
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import session

mail = Mail()
scheduler = APScheduler()
csrf = CSRFProtect()

# 1. Una key_func que identifique a cada uno por separado
def get_limit_key():
    if 'user_id' in session:
        return f"user_{session['user_id']}" # Cada admin tiene su propio límite
    return get_remote_address()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# 2. El "Pase VIP" (Sustituto de exempt_when)
@limiter.request_filter
def exempt_admins():
    return 'user_id' in session


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
    
    # Soporte para Proxys (Nginx, Gunicorn, Heroku, etc.)
    # Esto asegura que request.remote_addr sea la IP real del cliente.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    
    # Servir archivos estáticos en producción con WhiteNoise
    # En desarrollo (debug=True), Flask lo hace automáticamente.
    if not app.debug:
        static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        app.wsgi_app = WhiteNoise(app.wsgi_app, root=static_folder, prefix='static/')

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

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(429)
    def forbidden(e):
        return render_template('errors/429.html'), 429
    
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html'), 400

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
            'sub_status': None,
            'user': None,
            'is_admin': False
        }
        
        # Inyectar usuario si está en sesión
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    data['user'] = user
                    # Un usuario es admin si tiene un restaurante asociado
                    data['is_admin'] = user.restaurant is not None
        except Exception as e:
            pass
        
        restaurant = get_current_restaurant()
        if restaurant:
            try:
                data['sub_status'] = get_subscription_status(restaurant)
            except Exception as e:
                app.logger.error(f"Error fetching subscription status in context processor: {e}")
                data['sub_status'] = None
            
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
        user = None
        is_admin = False
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    is_admin = user.restaurant is not None
        except Exception:
            pass
        return render_template('errors/404.html', user=user, is_admin=is_admin), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        user = None
        is_admin = False
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    is_admin = user.restaurant is not None
        except Exception:
            pass
        return render_template('errors/500.html', user=user, is_admin=is_admin), 500

    @app.errorhandler(403)
    def forbidden(e):
        user = None
        is_admin = False
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    is_admin = user.restaurant is not None
        except Exception:
            pass
        return render_template('errors/403.html', user=user, is_admin=is_admin), 403

    return app

    
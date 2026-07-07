import os
from flask import Flask, render_template, session, request, flash, redirect, url_for
from .models import db, migrate,User
from flask_apscheduler import APScheduler
from flask_wtf.csrf import generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from whitenoise import WhiteNoise
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import session
from .extensions import scheduler, limiter
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from .csrf import csrf
from .routes.tokens import tokens_bp
from .routes.api_docs import api_docs_bp
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import can_perform_crud, get_subscription_status

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
    migrate.init_app(app, db)
    limiter.init_app(app)
    jwt = JWTManager(app)

    # IMPORTANTE: Registrar ANTES de csrf.init_app para que se ejecute primero.
    # Flask-WTF's _csrf_check internamente respeta request._csrf_exempt.
    @app.before_request
    def exempt_api_from_csrf():
        if request.path.startswith('/api/'):
            request._csrf_exempt = True

    csrf.init_app(app)
    
    # Habilitar CORS para permitir peticiones desde Scanner IA (Next.js/Node)
    CORS(app, resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",
                "http://localhost:5173",
                app.config.get('SCANNER_IA_URL', 'http://localhost:3000'),
            ],
            "supports_credentials": True
        }
    })
    
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
    from .routes.api_auth import api_auth_bp
    from .routes.api_dashboard import api_dashboard_bp
    from .routes.api_categories import api_categories_bp
    from .routes.api_products import api_products_bp
    from .routes.api_orders import api_orders_bp
    from .routes.api_public import api_public_bp
    from .routes.api_tables import api_tables_bp
    from .routes.api_email import api_email_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(tables_bp)
    app.register_blueprint(tokens_bp)
    app.register_blueprint(api_docs_bp)
    app.register_blueprint(api_auth_bp)
    app.register_blueprint(api_dashboard_bp)
    app.register_blueprint(api_categories_bp)
    app.register_blueprint(api_products_bp)
    app.register_blueprint(api_orders_bp)
    app.register_blueprint(api_public_bp)
    app.register_blueprint(api_tables_bp)
    app.register_blueprint(api_email_bp)
    csrf.exempt(api_email_bp)
    @app.before_request
    def block_grace_period_crud():
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if request.endpoint and ('auth.' in request.endpoint or 'payment' in request.endpoint or 'public.' in request.endpoint or 'api_auth.' in request.endpoint or request.path.startswith('/api/')):
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
        # Excluir archivos estáticos del no-cache para que WhiteNoise funcione
        if not request.path.startswith('/static'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '-1'
        return response

    @app.template_global()
    def get_image_url(image_path):
        if not image_path:
            return None
        if image_path.startswith('http'):
            return image_path
        return url_for('static', filename=image_path)

    # Inyectar variables de soporte y suscripción globalmente
    @app.context_processor
    def inject_global_data():
        data = {
            'SUPPORT_PHONE': app.config.get('SUPPORT_PHONE'),
            'SUPPORT_EMAIL': app.config.get('SUPPORT_EMAIL'),
            'SCANNER_IA_URL': app.config.get('SCANNER_IA_URL', 'http://localhost:3000'),
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
            app.logger.error(f"Error in template context processor: {e}")
        
        restaurant = get_current_restaurant()
        if restaurant:
            try:
                data['sub_status'] = get_subscription_status(restaurant)
            except Exception as e:
                app.logger.error(f"Error fetching subscription status in context processor: {e}")
                data['sub_status'] = None
            
        data['restaurant'] = restaurant
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
        except Exception as e:
            app.logger.error(f"Error in 404 handler: {e}")
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
        except Exception as e:
            app.logger.error(f"Error in 500 handler: {e}")
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
        except Exception as e:
            app.logger.error(f"Error in 403 handler: {e}")
        return render_template('errors/403.html', user=user, is_admin=is_admin), 403

    @app.errorhandler(429)
    def too_many_requests(e):
        user = None
        is_admin = False
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    is_admin = user.restaurant is not None
        except Exception as e:
            app.logger.error(f"Error in 429 handler: {e}")
        return render_template('errors/429.html', user=user, is_admin=is_admin), 429

    return app

    
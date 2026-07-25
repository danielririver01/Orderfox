import os
import logging
from flask import Flask, current_app, render_template, session, request, flash, redirect, url_for
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
from app.utils.subscription import can_perform_crud, get_subscription_status, PLAN_LIMITS

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

    # Logging configuration
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'), logging.INFO)
    logging.basicConfig(level=log_level)
    app.logger.setLevel(log_level)

    # Sentry / Better Stack Error Tracking initialization
    sentry_dsn = app.config.get('SENTRY_DSN')
    if sentry_dsn:
        import json
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        SENSITIVE_HEADERS = frozenset({
            'authorization', 'cookie', 'set-cookie',
            'x-api-key', 'x-auth-token', 'proxy-authorization',
        })
        SENSITIVE_BODY_KEYS = frozenset({
            'password', 'token', 'secret', 'api_key', 'authorization',
            'access_token', 'refresh_token', 'jwt', 'cookie', 'session',
        })

        def strip_sensitive_data(event, hint):
            if 'request' not in event:
                return event
            req = event['request']

            if req.get('data'):
                try:
                    body = json.loads(req['data'])
                    cleaned = {
                        k: ('***' if k.lower() in SENSITIVE_BODY_KEYS else v)
                        for k, v in body.items()
                    }
                    req['data'] = json.dumps(cleaned)
                except (json.JSONDecodeError, TypeError):
                    body_str = str(req['data']).lower()
                    if any(kw in body_str for kw in SENSITIVE_BODY_KEYS):
                        req['data'] = '***'

            headers = req.get('headers', {})
            if isinstance(headers, dict):
                for h in headers:
                    if h.lower() in SENSITIVE_HEADERS:
                        headers[h] = '***'

            return event

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FlaskIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
            before_send=strip_sensitive_data,
            traces_sample_rate=0,
            environment=app.config.get('FLASK_ENV', 'development'),
            release=app.config.get('APP_VERSION', 'unknown'),
        )
        app.logger.info('Better Stack Error Tracking initialized')

    # Disable auto-CSRF check; we run it manually for non-API routes below.
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    csrf.init_app(app)

    # Selective CSRF: skip /api/ and /insights/ routes (they use JWT not session).
    # csrf_protect runs first (set False above), then exempt_api runs,
    # then _csrf_protect_nonapi runs CSRF check for non-API routes.
    @app.before_request
    def exempt_api_from_csrf():
        if request.path.startswith('/api/') or request.path.startswith('/insights/api/'):
            return

    @app.before_request
    def _csrf_protect_nonapi():
        if request.path.startswith('/api/') or request.path.startswith('/insights/api/'):
            return
        csrf_instance = current_app.extensions.get('csrf')
        if csrf_instance:
            csrf_instance.protect()

    if sentry_dsn:
        from app.utils.jwt_auth import get_current_user_jwt
        from app.utils.restaurant import get_current_restaurant

        @app.before_request
        def set_sentry_context():
            user = get_current_user_jwt()
            if user:
                sentry_sdk.set_user({
                    'id': user.id,
                    'email': user.email,
                })
            restaurant = get_current_restaurant()
            if restaurant:
                sentry_sdk.set_tag('restaurant_id', restaurant.id)
            sentry_sdk.set_tag('app_version',
                               app.config.get('APP_VERSION', 'unknown'))
            module = request.path.split('/')[1] if request.path != '/' else 'root'
            sentry_sdk.set_tag('module', module)
    
    # Habilitar CORS para peticiones desde Astro (frontend moderno) y Scanner IA
    CORS(app, resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",
                "http://localhost:4321",
                "http://localhost:5173",
                app.config.get('SCANNER_IA_URL', 'http://localhost:3000'),
            ],
            "supports_credentials": True
        },
        r"/menu/api/*": {
            "origins": [
                "http://localhost:4321",
                "http://localhost:3000",
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
    from .routes.insights import insights_bp
    from .routes.public import public_bp
    from .routes.tables import tables_bp
    from .routes.api_auth import api_auth_bp
    from .routes.api_dashboard import api_dashboard_bp
    from .routes.api_categories import api_categories_bp
    from .routes.api_products import api_products_bp
    from .routes.api_orders import api_orders_bp
    from .routes.api_public import api_public_bp
    from .routes.api_tables import api_tables_bp
    from .routes.api_email import api_email_bp
    from .routes.api_webhooks import api_webhooks_bp
    from .routes.rewards import rewards_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(public_bp)
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
    app.register_blueprint(api_webhooks_bp)
    app.register_blueprint(rewards_bp)
    csrf.exempt(api_email_bp)
    csrf.exempt(rewards_bp)
    @app.before_request
    def block_grace_period_crud():
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if request.endpoint and ('auth.' in request.endpoint or 'payment' in request.endpoint or 'public.' in request.endpoint or 'api_auth.' in request.endpoint or request.path.startswith('/api/') or request.path.startswith('/insights/api/')):
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
        if not request.path.startswith('/static'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '-1'

        # Security headers
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '0'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "cdn.jsdelivr.net cdn.tailwindcss.com "
            "oriented-tortoise-50.clerk.accounts.dev clerk.velzia.shop; "
            "style-src 'self' 'unsafe-inline' "
            "fonts.googleapis.com cdn.jsdelivr.net; "
            "font-src 'self' fonts.gstatic.com data:; "
            "img-src 'self' data: res.cloudinary.com img.clerk.com; "
            "connect-src 'self' oriented-tortoise-50.clerk.accounts.dev clerk.velzia.shop; "
            "frame-src 'self' oriented-tortoise-50.clerk.accounts.dev clerk.velzia.shop; "
            "worker-src 'self' blob:"
        )

        # HSTS solo si no está en debug
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # No leak server version
        response.headers.pop('Server', None)

        return response

    @app.template_global()
    def get_image_url(image_path):
        if not image_path:
            return None
        if image_path.startswith('http'):
            return image_path
        return url_for('static', filename=image_path)

    @app.template_filter('currency')
    def currency_filter(value):
        if value is None:
            return '$0'
        try:
            n = int(value)
            return '$' + f"{n:,}".replace(',', '.')
        except (ValueError, TypeError):
            return '$0'

    # Inyectar variables de soporte y suscripción globalmente
    @app.context_processor
    def inject_global_data():
        from app.utils.restaurant import get_current_restaurant
        from app.utils.subscription import get_subscription_status, PLAN_LIMITS
        
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
        if restaurant:
            data['plan_name'] = PLAN_LIMITS.get(restaurant.plan_type, {}).get('name', restaurant.plan_type.capitalize())
        else:
            data['plan_name'] = None
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
        app.logger.error(f"Internal server error: {e}", exc_info=True)
        user = None
        is_admin = False
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    is_admin = user.restaurant is not None
        except Exception as e2:
            app.logger.error(f"Error in 500 handler: {e2}")
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

    
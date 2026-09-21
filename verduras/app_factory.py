"""
Factory de la app Verduras.

Simétrica a `app.create_app()` de core, pero mínima: este módulo es solo
presentación + lógica de su vertical. La DB es la compartida (contrato del
puente); no registra migraciones propias ni schedulers (eso sigue viviendo
en core).

Uso:
    cd verduras
    ../.venv/Scripts/python run.py     # http://localhost:5100
"""
import logging
import os

from flask import Flask, jsonify, request

from .extensions import csrf, db, migrate
from .settings import Config


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    # CSRF manual (mismo patrón que core): las APIs JSON van con x-api-key
    # y quedan exentas; el dashboard POS valida vía el guard de abajo.
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    csrf.init_app(app)

    @app.before_request
    def _pos_csrf_guard():
        """CSRF en los POST del dashboard (login, logout, venta por sesión).

        Las rutas /api/* van con x-api-key y quedan fuera del guard (mismo
        criterio de core: CSRF para formularios con sesión, no para APIs
        autenticadas por header). Respeta WTF_CSRF_ENABLED (los tests lo
        apagan; protect() directo no lo consulta por sí solo).
        """
        if (request.method == 'POST' and request.blueprint == 'dashboard'
                and not request.path.startswith('/api/')
                and app.config.get('WTF_CSRF_ENABLED', True)):
            csrf.protect()

    db.init_app(app)
    # Directorio de migraciones PROPIO del módulo (aún no existe): si alguien
    # corre `flask db ...` desde la app verduras, falla ruidoso en vez de
    # ejecutar por accidente las migraciones de core. Core es dueño del
    # esquema de tablas compartidas (ver verduras/README.md).
    _module_migrations = os.path.join(os.path.dirname(__file__), 'migrations')
    migrate.init_app(app, db, directory=_module_migrations)

    # Los listeners del puente Business ↔ Restaurant se registran al importar
    # app.models (hecho vía verduras.extensions). Esta importación explícita
    # documenta la dependencia y asegura el registro aunque extensions cambie.
    # Registra las tablas verduras_* en el metadata compartido (orden matters:
    # debe importarse antes de create_all/migrate autogenerate).
    import verduras.models
    import verduras.models_inventory
    import verduras.models_sales  # noqa: F401
    from app.models import Business, Restaurant  # noqa: F401

    from .routes.businesses import businesses_bp
    from .routes.catalog import catalog_bp
    from .routes.dashboard import dashboard_bp
    from .routes.health import health_bp
    from .routes.inventory import inventory_bp
    from .routes.sales import sales_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(businesses_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(dashboard_bp)

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(success=False, error_code='not_found'), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify(success=False, error_code='internal_error'), 500

    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'), logging.INFO)
    logging.basicConfig(level=log_level)
    app.logger.setLevel(log_level)

    # Healthcheck en raíz para orquestadores
    @app.route('/')
    def index():
        return jsonify(
            success=True,
            module=app.config['MODULE_NAME'],
            version=app.config['MODULE_VERSION'],
        )

    return app

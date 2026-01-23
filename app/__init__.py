from flask import Flask
from .models import db, migrate


def create_app():
    app = Flask(__name__, template_folder='template')
    app.config.from_object('settings.Config')
    db.init_app(app)

    #Registramos blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.categories import categories_bp
    from .routes.products import products_bp
    from .routes.orders import orders_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)

    migrate.init_app(app, db)

    return app

    
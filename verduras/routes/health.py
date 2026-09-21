"""Healthcheck del módulo Verduras: proceso + conexión a la DB compartida."""
from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.models import Business

from ..extensions import db

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health():
    """Liveness/readiness del módulo. Verifica DB compartida con core."""
    db_ok = True
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        db_ok = False
        current_app.logger.exception("Healthcheck: DB compartida inaccesible")

    status = 200 if db_ok else 503
    return jsonify(
        success=db_ok,
        module=current_app.config['MODULE_NAME'],
        version=current_app.config['MODULE_VERSION'],
        database=db_ok,
    ), status


@health_bp.route('/health/core-bridge', methods=['GET'])
def core_bridge():
    """Diagnóstico del puente: cuenta espejos de restaurantes y del vertical."""
    mirrors = Business.query.filter_by(vertical='restaurant').count()
    verduras = Business.query.filter_by(vertical='verduras').count()
    return jsonify(
        success=True,
        bridge={'restaurant_mirrors': mirrors, 'verduras_businesses': verduras},
    )

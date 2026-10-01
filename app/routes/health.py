"""Endpoint de salud para monitoreo y despliegues (R-15 / VLZ-13).

Lo consumen systemd, `deploy/update_server.sh` (paso 6) y cualquier monitor
externo. Verifica de verdad que la app está viva — la conexión a la base de
datos — porque un proceso que responde 200 con la BD caída no está "sano".

A propósito no expone nada más (ni versión, ni contadores): un endpoint de
salud público no debe regalar huellas del stack.
"""
from flask import Blueprint, jsonify
from sqlalchemy.exc import SQLAlchemyError

from app.models import db

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
    except SQLAlchemyError:  # BD caída, pool agotado, timeout: todo es "down"
        return jsonify({'status': 'error', 'db': 'down'}), 503
    return jsonify({'status': 'ok', 'db': 'ok'}), 200

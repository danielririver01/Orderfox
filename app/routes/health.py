"""Endpoint de salud para monitoreo y despliegues (R-15 / VLZ-13).

Lo consumen systemd, `deploy/update_server.sh` (paso 6) y cualquier monitor
externo. Verifica de verdad que la app está viva — la conexión a la base de
datos y, cuando el rate limiter usa Redis como storage compartido (VLZ-16),
también un PING a Redis — porque con el fallback de memoria activado, un
Redis caído es una degradación silenciosa que este endpoint debe delatar.

A propósito no expone nada más (ni versión, ni contadores): un endpoint de
salud público no debe regalar huellas del stack.
"""
import os

from flask import Blueprint, jsonify
from sqlalchemy.exc import SQLAlchemyError

from app.models import db

health_bp = Blueprint('health', __name__)

REDIS_TIMEOUT_SECONDS = 1


def _redis_status():
    """PING a Redis si está configurado como storage; None si no lo está."""
    url = os.getenv('RATELIMIT_STORAGE_URL') or ''
    if not url.startswith('redis://'):
        return None
    # Import perezoso: entornos sin Redis configurado no necesitan la lib.
    import redis
    try:
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
            retry_on_timeout=False,
        )
        ok = bool(client.ping())
    except (redis.RedisError, ValueError):
        ok = False
    return 'ok' if ok else 'down'


@health_bp.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
    except SQLAlchemyError:  # BD caída, pool agotado, timeout: todo es "down"
        return jsonify({'status': 'error', 'db': 'down'}), 503

    redis_status = _redis_status()
    if redis_status == 'down':
        # La BD está bien pero el smoke test del deploy debe ver esto.
        return jsonify({'status': 'error', 'db': 'ok', 'redis': 'down'}), 503

    body = {'status': 'ok', 'db': 'ok'}
    if redis_status:
        body['redis'] = redis_status
    return jsonify(body), 200

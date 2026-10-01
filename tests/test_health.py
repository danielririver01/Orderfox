"""Endpoint /health (R-15 / VLZ-13).

La app puede responder con la BD caída y eso no es "estar sana": el endpoint
verifica la conexión de verdad. Lo consumen systemd, update_server.sh (paso 6)
y monitores externos.
"""
from unittest import mock

from sqlalchemy.exc import SQLAlchemyError


class TestHealth:

    def test_health_ok(self, client):
        res = client.get('/health')
        assert res.status_code == 200
        body = res.get_json()
        assert body == {'status': 'ok', 'db': 'ok'}

    def test_health_with_db_down_returns_503(self, client):
        """Regresión: 200 con la BD caída es exactamente lo que R-15 denuncia."""
        with mock.patch('app.routes.health.db') as fake_db:
            fake_db.session.execute.side_effect = SQLAlchemyError('conexion caida')
            res = client.get('/health')
        assert res.status_code == 503
        assert res.get_json() == {'status': 'error', 'db': 'down'}

    def test_health_rejects_post(self, client):
        """POST cae en el CSRF global (redirect) antes del 405: /health es de
        solo lectura para monitores — lo importante es que no sirve datos."""
        res = client.post('/health')
        assert res.status_code != 200
        assert res.get_json(silent=True) is None

    def test_health_is_registered_in_the_app(self, client):
        """El nginx de prod excluye 'health' del enrutador de slugs; si la
        ruta dejara de existir, /health caería al redirect del menú público."""
        rules = [r.rule for r in client.application.url_map.iter_rules()]
        assert '/health' in rules

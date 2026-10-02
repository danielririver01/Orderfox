"""Alcance del "Pase VIP" de Flask-Limiter (R-08 / VLZ-16).

El VIP (sesión iniciada) exime de los límites GLOBALES — los defaults están
pensados para tráfico anónimo y aplicarlos al dashboard lo rompería — pero NO
de los guards por-ruta (login PIN de empleados, rewards/claim).

Antes el VIP era un `request_filter` global: cualquier sesión iniciada
sorteaba TODO, incluido el anti-fuerza-bruta del login de empleados.
"""
import re

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.extensions import default_limits_exempt


def _mini_app():
    """App mínima con la MISMA semántica de exención que el proyecto real."""
    app = Flask(__name__)
    app.secret_key = 'test'
    app.config['TESTING'] = True
    mini = Limiter(
        key_func=get_remote_address,
        default_limits=['3 per day'],
        storage_uri='memory://',
        default_limits_exempt_when=default_limits_exempt,
    )
    mini.init_app(app)

    @app.route('/libre')
    def libre():
        return 'ok'

    @app.route('/protegido')
    @mini.limit('2 per minute')
    def protegido():
        return 'ok'

    return app


class TestVipExemptFromDefaults:

    def test_anonymous_hits_the_default_limit(self):
        client = _mini_app().test_client()
        for _ in range(3):
            assert client.get('/libre').status_code == 200
        assert client.get('/libre').status_code == 429

    def test_logged_in_session_bypasses_defaults(self):
        client = _mini_app().test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 42
        for _ in range(6):  # más que el default de 3/día
            assert client.get('/libre').status_code == 200


class TestVipDoesNotBypassRouteGuards:

    def test_logged_in_session_still_hits_the_route_limit(self):
        client = _mini_app().test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 42
        assert client.get('/protegido').status_code == 200
        assert client.get('/protegido').status_code == 200
        assert client.get('/protegido').status_code == 429

    def test_employee_pin_login_429s_even_with_user_session(
            self, client, sample_restaurant):
        """Regresión de R-08: el anti-fuerza-bruta del login PIN aplica
        SIEMPRE. Con el request_filter global de antes, una sesión iniciada
        sorteaba este guard y este test fallaría."""
        # IP propia vía X-Forwarded-For (ProxyFix x_for=1): el contador de
        # 5/min queda aislado del resto de la suite.
        headers = {'X-Forwarded-For': '10.99.99.16'}
        with client.session_transaction() as sess:
            sess['user_id'] = 1

        # El token CSRF se toma UNA vez: cada GET también cuenta para el
        # límite de 5/min de esta ruta (7 peticiones en total → 429 seguro).
        page = client.get(f'/empleado/{sample_restaurant.slug}', headers=headers)
        token = re.search(
            r'name="csrf-token" content="([^"]+)"',
            page.get_data(as_text=True),
        )
        assert token, f'La página de login no trajo csrf-token: {page.status_code}'

        codes = [client.post(
            f'/empleado/{sample_restaurant.slug}',
            data={'csrf_token': token.group(1), 'pin': '0000'},
            headers=headers,
        ).status_code for _ in range(6)]
        assert 429 in codes, (
            f'El login PIN no aplicó el límite ni con 6 intentos: {codes}'
        )


class TestStorageFallback:

    def test_unreachable_redis_degrades_to_memory_not_500(self):
        """Redis caído no tumba la app (VLZ-16): con el fallback activo los
        requests siguen respondiendo y el límite sigue aplicando, ahora con
        contadores en memoria. Puerto 1: nunca hay nadie escuchando ahí."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        mini = Limiter(
            key_func=get_remote_address,
            default_limits=['3 per day'],
            storage_uri='redis://localhost:1/0',
            in_memory_fallback_enabled=True,
        )
        mini.init_app(app)

        @app.route('/libre')
        def libre():
            return 'ok'

        client = app.test_client()
        for _ in range(3):
            assert client.get('/libre').status_code == 200
        assert client.get('/libre').status_code == 429

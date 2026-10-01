"""Regla anti-bot de 3 s (RN-02) con token firmado — R-17 / VLZ-21.

Regresión del fallo original: la marca de tiempo vivía en la **sesión de Flask**,
que no viaja al frontend Astro (que se sirve en otro origen), así que un bot que
nunca llamaba a ``init-checkout`` se colaba con un 200 — la comprobación era
inerte. Ahora el token va firmado por el servidor y es **obligatorio**.

La edad del token se simula con la fixture ``checkout_clock`` / ``checkout_ready``
(ver ``tests/conftest.py``): 0 s reales de espera.
"""
import pytest
from itsdangerous import URLSafeTimedSerializer

from app.utils.checkout_token import (
    MAX_AGE_SECONDS,
    MIN_SECONDS,
    elapsed_seconds,
    issue_checkout_token,
)


def _post_order(client, restaurant, product, token=None, with_token=True):
    body = {
        'restaurant_id': restaurant.id,
        'cart': {str(product.id): {'quantity': 1, 'extras': []}},
        'customer_name': 'Cliente Test',
        'customer_phone': '+573001234567',
    }
    if with_token:
        body['checkout_token'] = token
    return client.post('/menu/api/order', json=body)


# ── init-checkout ───────────────────────────────────────────────────────────

class TestInitCheckout:

    def test_returns_a_token(self, client):
        res = client.post('/menu/api/init-checkout')
        assert res.status_code == 200
        body = res.get_json()
        assert body['success'] is True
        assert isinstance(body['checkout_token'], str)
        assert body['checkout_token']

    def test_does_not_write_to_the_flask_session(self, client):
        """La sesión ya no lleva la marca de tiempo: por eso no viajaba a Astro."""
        client.post('/menu/api/init-checkout')
        with client.session_transaction() as sess:
            assert 'checkout_start_time' not in sess

    def test_token_survives_a_different_client(self, app, client, sample_restaurant,
                                              sample_product, checkout_ready):
        """Criterio de cierre: el token NO depende de la sesión del emisor.

        Se emite con un cliente y se consume con otro, sin cookies compartidas:
        es exactamente el cruce cross-origin del menú público (Astro → API).
        """
        with checkout_ready() as token:
            otro = app.test_client()
            res = _post_order(otro, sample_restaurant, sample_product, token=token)
        assert res.status_code == 200, res.get_data(as_text=True)


# ── La regla bloquea ─────────────────────────────────────────────────────────

class TestRuleBlocks:

    def test_bot_without_init_checkout_is_blocked(self, client, sample_restaurant,
                                                  sample_product):
        """Regresión de R-17: sin token (lo que hacía un bot) ya no hay 200."""
        res = _post_order(client, sample_restaurant, sample_product, with_token=False)
        assert res.status_code == 429
        assert 'expiró' in res.get_json()['error']

    def test_empty_token_is_blocked(self, client, sample_restaurant, sample_product):
        res = _post_order(client, sample_restaurant, sample_product, token='')
        assert res.status_code == 429

    def test_tampered_token_is_blocked(self, client, sample_restaurant, sample_product,
                                       checkout_ready):
        with checkout_ready() as token:
            res = _post_order(client, sample_restaurant, sample_product,
                              token=token + 'x')
        assert res.status_code == 429
        assert 'expiró' in res.get_json()['error']

    def test_token_signed_with_another_secret_is_blocked(self, client, sample_restaurant,
                                                         sample_product, checkout_clock):
        """Un token firmado con otro SECRET_KEY no vale (falsificación)."""
        with checkout_clock(10):
            falso = URLSafeTimedSerializer(
                'clave-de-otro-servidor', salt='velzia-checkout-v1').dumps({'v': 1})
            res = _post_order(client, sample_restaurant, sample_product, token=falso)
        assert res.status_code == 429
        assert 'expiró' in res.get_json()['error']

    def test_fresh_token_is_too_fast(self, client, sample_restaurant, sample_product,
                                     checkout_ready):
        with checkout_ready(0) as token:
            res = _post_order(client, sample_restaurant, sample_product, token=token)
        assert res.status_code == 429
        assert 'muy rápido' in res.get_json()['error']

    def test_token_just_under_the_minimum_is_blocked(self, client, sample_restaurant,
                                                     sample_product, checkout_ready):
        # Margen de 1,5 s: la marca de tiempo de itsdangerous es de segundos
        # enteros, así que la edad real cae en [1,5 - 0,5) s.
        with checkout_ready(MIN_SECONDS - 1.5) as token:
            res = _post_order(client, sample_restaurant, sample_product, token=token)
        assert res.status_code == 429
        assert 'muy rápido' in res.get_json()['error']

    def test_expired_token_is_blocked(self, client, sample_restaurant, sample_product,
                                      checkout_ready):
        """Checkout abandonado: pasado el vencimiento el token no sirve."""
        with checkout_ready(MAX_AGE_SECONDS + 60) as token:
            res = _post_order(client, sample_restaurant, sample_product, token=token)
        assert res.status_code == 429
        assert 'expiró' in res.get_json()['error']


# ── La regla deja pasar ──────────────────────────────────────────────────────

class TestRuleAllows:

    def test_token_older_than_the_minimum_is_accepted(self, client, sample_restaurant,
                                                      sample_product, checkout_ready):
        with checkout_ready(MIN_SECONDS + 1.5) as token:
            res = _post_order(client, sample_restaurant, sample_product, token=token)
        assert res.status_code == 200, res.get_data(as_text=True)
        assert res.get_json()['success'] is True

    def test_honeypot_still_wins_over_a_valid_token(self, client, sample_restaurant,
                                                    sample_product, checkout_ready):
        """La defense en profundidad se mantiene: honeypot (403) + 3 s (429)."""
        with checkout_ready(10) as token:
            res = client.post('/menu/api/order', json={
                'restaurant_id': sample_restaurant.id,
                'cart': {str(sample_product.id): {'quantity': 1, 'extras': []}},
                'customer_name': 'Bot',
                'user_secondary_email': 'bot@spam.example',
                'checkout_token': token,
            })
        assert res.status_code == 403
        assert 'sospechosa' in res.get_json()['error']


# ── El helper por dentro ─────────────────────────────────────────────────────

class TestElapsedSeconds:

    def test_minimum_is_the_documented_three_seconds(self):
        assert MIN_SECONDS == 3.0

    def test_fresh_token_has_zero_elapsed(self, app):
        # Entre 0 y 1 s: su marca de tiempo es de segundos enteros.
        with app.test_request_context():
            elapsed = elapsed_seconds(issue_checkout_token())
        assert 0 <= elapsed < 1

    @pytest.mark.parametrize('token', ['', 'no-es-un-token', 'a.b.c'])
    def test_invalid_tokens_return_none(self, app, token):
        with app.test_request_context():
            assert elapsed_seconds(token) is None

    def test_counts_the_aged_seconds(self, app, checkout_clock):
        with app.test_request_context():
            token = issue_checkout_token()
            with checkout_clock(7):
                elapsed = elapsed_seconds(token)
        assert 7 <= elapsed < 8

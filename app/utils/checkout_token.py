"""Token de checkout firmado (stateless) para el anti-bot de 3 s (RN-02).

Por qué no basta la sesión de Flask
-----------------------------------
El menú público lo sirve el frontend Astro **standalone**, en otro origen que la
API (``menu.velzia.shop`` vs. el dominio de Flask). La cookie de sesión no
viaja de forma fiable en ese cruce, así que la marca de tiempo del checkout se
lleva dentro de un **token firmado por el servidor** en vez de en la sesión.

El token se emite en ``POST /menu/api/init-checkout`` y el cliente lo devuelve
al crear el pedido. Como es autocontenido, funciona cross-origin sin cookies y
no deja estado en el servidor.

Contrato
--------
* ``issue_checkout_token()`` → token recién emitido (edad 0 s).
* ``elapsed_seconds(token)`` → segundos transcurridos desde la emisión, o
  ``None`` si el token falta, está alterado o superó la vigencia máxima.
"""
from datetime import datetime, timezone

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer

# Segundos mínimos entre abrir el checkout y enviar el pedido (RN-02).
MIN_SECONDS = 3.0

# Vigencia máxima del token. Un checkout abandoned no debe dejar un token
# utilizable para siempre, así que 30 min es holgado y suficiente.
MAX_AGE_SECONDS = 1800

_SALT = 'velzia-checkout-v1'


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def issue_checkout_token() -> str:
    """Emite un token de checkout nuevo (edad 0 s)."""
    return _serializer().dumps({'v': 1})


def elapsed_seconds(token: str) -> float | None:
    """Segundos desde que se emitió ``token``.

    Devuelve ``None`` si el token no es válido: ausente, con la firma alterada,
    emitido con otro ``SECRET_KEY`` o vencido (más de ``MAX_AGE_SECONDS``).

    El vencimiento se comprueba aquí y no con el ``max_age`` de itsdangerous a
    propósito: aquel usa su propio ``time.time()`` y la regla debe apoyarse en
    un único reloj. Ojo también con que su marca de tiempo es de **segundos
    enteros**: un token recién emitido tiene entre 0 y 1 s de antigüedad.
    """
    if not token:
        return None
    try:
        _, issued_at = _serializer().loads(token, return_timestamp=True)
    except BadSignature:
        return None
    if issued_at.tzinfo is None:  # pragma: no cover - itsdangerous devuelve aware
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - issued_at).total_seconds()
    return None if elapsed > MAX_AGE_SECONDS else elapsed

"""
mp_webhook.py — Utilidades compartidas para webhooks de Mercado Pago.

Centraliza la verificación de firma HMAC-SHA256 y el parseo del
header `x-signature` para que cualquier endpoint de webhook (nuevo o
existente) pueda validar que la notificación viene realmente de MP.
"""

import hmac
import hashlib


def extract_mp_signature(headers) -> tuple:
    """Extrae ts y v1 del header `x-signature` de Mercado Pago.

    Formato esperado: `ts=<unix>,v1=<hex>,v2=...`
    Retorna (ts, v1) o (None, None) si no se encuentra el header.
    """
    sig_header = headers.get('x-signature') or headers.get('X-Signature') or ''
    if not sig_header:
        return None, None

    ts = None
    v1 = None
    for part in sig_header.split(','):
        part = part.strip()
        if part.startswith('ts='):
            ts = part[3:]
        elif part.startswith('v1='):
            v1 = part[3:]
    return ts, v1


def verify_mp_signature(data_id: str, ts: str, v1: str, secret: str) -> bool:
    """Verifica HMAC-SHA256 de la firma `x-signature` de MP Webhooks API.

    Construcción del mensaje: `data_id + '.' + ts + '.' + secret`.
    Compara el HMAC con `v1` (hex digest) usando `hmac.compare_digest`
    (resistente a timing attacks).
    """
    if not all([data_id, ts, v1, secret]):
        return False

    message = f"{data_id}.{ts}.{secret}"
    expected = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, v1)

"""
mp_webhook.py — Utilidades compartidas para webhooks de Mercado Pago.

Centraliza la verificación de firma HMAC-SHA256 y el parseo de las cabeceras
`x-signature` y `x-request-id`, para que cualquier endpoint de webhook (nuevo o
existente) pueda validar que la notificación viene realmente de MP.

El esquema implementado es el **oficial de Mercado Pago**:

    manifiesto = "id:<data.id>;request-id:<x-request-id>;ts:<ts>;"
    v1_esperado = HMAC-SHA256(clave_secreta, manifiesto).hexdigest()

Notas de la especificación que conviene no perder de vista:

- Los pares cuyo valor no llegue en la notificación **se omiten** del
  manifiesto (no se escriben vacíos).
- `data.id` va en **minúsculas**. Para los pagos es numérico y da igual, pero
  otros recursos usan identificadores alfanuméricos.
- `data.id` puede venir en el cuerpo o en el *query param*; quien llame a
  `verify_mp_signature` debe resolverlo antes.
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
            ts = part[3:].strip()
        elif part.startswith('v1='):
            v1 = part[3:].strip()
    return ts, v1


def extract_mp_request_id(headers) -> str:
    """Devuelve el header `x-request-id`, que forma parte del manifiesto.

    Sin este valor la firma de una notificación real nunca cuadra, porque MP
    lo incluye al calcularla.
    """
    return headers.get('x-request-id') or headers.get('X-Request-Id') or None


def build_mp_manifest(data_id, request_id, ts) -> str:
    """Construye el manifiesto que Mercado Pago firma.

    Formato oficial: `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`
    Los pares sin valor se omiten, tal y como especifica MP.
    """
    partes = []
    if data_id:
        partes.append(f"id:{str(data_id).lower()};")
    if request_id:
        partes.append(f"request-id:{request_id};")
    if ts:
        partes.append(f"ts:{ts};")
    return ''.join(partes)


def verify_mp_signature(data_id, request_id, ts, v1, secret) -> bool:
    """Verifica la firma `x-signature` de una notificación de Mercado Pago.

    Compara el HMAC-SHA256 del manifiesto oficial contra `v1` usando
    `hmac.compare_digest` (resistente a timing attacks).

    Devuelve False ante cualquier dato ausente: sin firma, sin secreto o sin
    ningún componente del manifiesto no hay nada que validar.
    """
    if not v1 or not secret:
        return False

    manifiesto = build_mp_manifest(data_id, request_id, ts)
    if not manifiesto:
        return False

    esperado = hmac.new(
        secret.encode('utf-8'),
        manifiesto.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(esperado, v1.strip().lower())

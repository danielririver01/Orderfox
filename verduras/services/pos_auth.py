"""
Auth del POS (dashboard del tendero) por sesión: slug + PIN.

Por qué existe: la SERVICE_API_KEY es server-to-server (core llama a core).
El POS corre en el NAVEGADOR del tendero — si usara la key, cualquiera con
DevTools podría verla y operar el negocio. El login es entonces slug + PIN
con sesión firmada por Flask; la key jamás llega al cliente.

El PIN vive en `verduras_business_settings` (tabla PROPIA del módulo): core
es dueño del esquema de `businesses` y el módulo no le agrega columnas.

- PIN 4-6 dígitos, hasheado con werkzeug (nunca plano).
- Máx 5 intentos por IP+negocio → lock de 10 min (en memoria, mismo
  trade-off del rate limiter de core: se pierde al reiniciar).
- Mensaje de login genérico: no se revela si falló el slug o el PIN.
"""
import secrets
import time
from datetime import datetime, timezone

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db
from verduras.models_sales import VerdurasBusinessSettings
from verduras.services.context import get_business, get_business_by_slug

SESSION_KEY = 'pos_business_id'
MAX_ATTEMPTS = 5
LOCK_MINUTES = 10

# {(business_id, ip): {'n': int, 'locked_until': float}}
_failed: dict = {}


class PosAuthError(ValueError):
    """Login/autorización del POS rechazada (mensaje amable incluido)."""


def _validate_pin(pin) -> str:
    if pin is None or not str(pin).strip().isdigit():
        raise PosAuthError('El PIN debe ser numérico')
    pin = str(pin).strip()
    if not 4 <= len(pin) <= 6:
        raise PosAuthError('El PIN debe tener entre 4 y 6 dígitos')
    return pin


def _settings_row(business_id: int) -> VerdurasBusinessSettings | None:
    return db.session.get(VerdurasBusinessSettings, business_id)


def has_pos_pin(business_id: int) -> bool:
    row = _settings_row(business_id)
    return bool(row and row.pos_pin_hash)


def setup_pos_pin(business_id: int, pin) -> None:
    """Configura o actualiza el PIN del POS (hash, nunca plano).

    Se llama vía API server-to-server (x-api-key): el onboarding del
    dashboard de core provisiona el PIN; el tendero solo lo usa.
    """
    business = get_business(business_id)
    if business is None or business.vertical != 'verduras':
        raise PosAuthError('Negocio no encontrado')  # no revelar verticales
    pin = _validate_pin(pin)

    row = _settings_row(business_id)
    if row is None:
        row = VerdurasBusinessSettings(business_id=business_id)
        db.session.add(row)
    row.pos_pin_hash = generate_password_hash(pin)
    row.pos_pin_updated_at = datetime.now(timezone.utc)
    db.session.commit()


def get_setup_target(slug, token):
    """Business con token de setup VÁLIDO, o PosAuthError (enlace muerto)."""
    business = get_business_by_slug(str(slug or '').strip())
    stored = (business.pos_setup_token
              if business is not None and business.vertical == 'verduras'
              else None)
    if (not stored
            or not secrets.compare_digest(stored, str(token or '').strip())):
        raise PosAuthError(
            'Este enlace de configuración no es válido o ya fue usado')
    return business


def consume_setup_token(slug, token, pin, whatsapp_phone=None):
    """Setup del POS con token de UN SOLO USO (emitido por core al registrar).

    Flujo self-service: core crea el Business y deja el token en
    `businesses.pos_setup_token` (DB compartida = canal del monorepo); el
    dueño abre /pos/setup/<slug>/<token>, elige PIN y WhatsApp, y el token
    se limpia en la misma operación — el enlace muere tras usarse.
    """
    business = get_setup_target(slug, token)
    setup_pos_pin(business.id, pin)  # valida PIN y vertical (mismo patrón)
    if whatsapp_phone:
        from verduras.services.sales import update_settings
        update_settings(business.id,
                        {'whatsapp_phone': str(whatsapp_phone).strip()})
    business.pos_setup_token = None  # un solo uso
    db.session.commit()
    return business


def login_pos(slug, pin, ip=None):
    """Autentica slug + PIN y deja la sesión del POS. Devuelve el Business."""
    slug = str(slug or '').strip()
    pin = str(pin or '').strip()
    business = get_business_by_slug(slug)
    if (business is None or business.vertical != 'verduras'
            or not business.is_active):
        raise PosAuthError('Negocio o PIN incorrecto')

    row = _settings_row(business.id)
    if not row or not row.pos_pin_hash:
        raise PosAuthError('Este negocio aún no configura su PIN de POS')

    key = (business.id, ip or '')
    state = _failed.get(key) or {}
    if state.get('locked_until', 0) > time.time():
        raise PosAuthError(
            'Demasiados intentos: espera unos minutos y vuelve a intentar')

    if not check_password_hash(row.pos_pin_hash, pin):
        attempts = state.get('n', 0) + 1
        if attempts >= MAX_ATTEMPTS:
            _failed[key] = {
                'n': 0,
                'locked_until': time.time() + LOCK_MINUTES * 60,
            }
        else:
            _failed[key] = {'n': attempts}
        raise PosAuthError('Negocio o PIN incorrecto')

    _failed.pop(key, None)
    session[SESSION_KEY] = business.id
    session.permanent = True
    return business


def logout_pos() -> None:
    session.pop(SESSION_KEY, None)


def current_pos_business():
    """Business con sesión activa del POS, o None (valida vertical/activo)."""
    business_id = session.get(SESSION_KEY)
    if business_id is None:
        return None
    business = get_business(business_id)
    if (business is None or business.vertical != 'verduras'
            or not business.is_active):
        return None
    return business


def require_pos_business():
    """current_pos_business o levanta PosAuthError (la ruta redirige al login)."""
    business = current_pos_business()
    if business is None:
        raise PosAuthError('Sesión del POS no iniciada')
    return business

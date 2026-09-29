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
from datetime import datetime, timedelta, timezone

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db
from verduras.models_sales import VerdurasBusinessSettings
from verduras.services.context import (
    find_business_by_identifier,
    get_business,
    get_business_by_slug,
)

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


def change_pos_pin(business_id: int, current_pin, new_pin) -> None:
    """Cambia el PIN del mostrador verificando el actual (Config v1).

    Sin el PIN vigente no hay cambio (el tendero lo sabe; un extraño no).
    Reutiliza la validación de formato y el hash de setup_pos_pin. Los
    intentos fallidos aquí NO tocan el lockout de login (ese protege la
    puerta; esto es un cambio autenticado en sesión).
    """
    business = get_business(business_id)
    if business is None or business.vertical != 'verduras':
        raise PosAuthError('Negocio no encontrado')
    row = _settings_row(business_id)
    if not row or not row.pos_pin_hash:
        raise PosAuthError('Este negocio aún no configura su PIN de POS')
    if not check_password_hash(row.pos_pin_hash, str(current_pin or '')):
        raise PosAuthError('El PIN actual no coincide')
    setup_pos_pin(business_id, new_pin)


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


# ── Handoff Mundos → POS (dueño salta sin PIN) ──────────────────────────

SSO_TTL_MINUTES = 5


def mint_pos_sso_token(business_id: int) -> str:
    """Emite token de handoff Mundos→POS (un solo uso, expira en 5 min).

    Lo llama core con sesión de dueño YA verificada (el dueño es el emisor,
    no el presentador). Reemplaza el anterior: solo un token vivo a la vez.
    El token NUNCA se loguea.
    """
    business = get_business(business_id)
    if (business is None or business.vertical != 'verduras'
            or not business.is_active):
        raise PosAuthError('Negocio no encontrado')  # no revelar verticales
    token = secrets.token_urlsafe(32)
    business.pos_sso_token = token
    business.pos_sso_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=SSO_TTL_MINUTES))
    db.session.commit()
    return token


def consume_pos_sso_token(slug, token):
    """Consume el handoff: valida, limpia y deja la sesión del POS.

    Mensaje genérico: no revela si falló el slug, el token o la expiración.
    El token expirado también se limpia (no deja basura válida a medias).
    """
    slug = str(slug or '').strip()
    token = str(token or '').strip()
    business = get_business_by_slug(slug)
    stored = (business.pos_sso_token
              if business is not None and business.vertical == 'verduras'
              else None)
    if not stored or not secrets.compare_digest(stored, token):
        raise PosAuthError('Este enlace ya fue usado o expiró')
    if not business.is_active:
        raise PosAuthError('Este enlace ya fue usado o expiró')
    expires = business.pos_sso_expires_at
    if expires is not None:
        if expires.tzinfo is None:  # defensivo: DATETIME sin tz en MySQL viejo
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            business.pos_sso_token = None
            business.pos_sso_expires_at = None
            db.session.commit()
            raise PosAuthError('Este enlace ya fue usado o expiró')
    business.pos_sso_token = None  # un solo uso
    business.pos_sso_expires_at = None
    db.session.commit()
    session[SESSION_KEY] = business.id
    session.permanent = True
    return business


def request_pos_pin_reset(email: str, base_url: str = '') -> tuple[bool, str]:
    """Genera token de restablecimiento de PIN y envía enlace por correo.

    Protege contra enumeración de cuentas: siempre devuelve mensaje de éxito genérico.
    """
    msg_generic = (
        'Si el correo electrónico está registrado, recibirás un enlace '
        'para restablecer tu PIN en unos minutos.'
    )
    if not email or '@' not in str(email):
        return True, msg_generic

    clean_email = str(email).strip().lower()
    from sqlalchemy import func
    from app.models import Business, User
    from app.services.mail_service import send_email

    user = User.query.filter(func.lower(User.email) == clean_email).first()
    if not user:
        return True, msg_generic

    biz = Business.query.filter(
        Business.vertical == 'verduras',
        db.or_(
            Business.owner_user_id == user.id,
            Business.id == user.restaurant_id,
        ),
        Business.is_active.is_(True),
    ).first()

    if not biz:
        return True, msg_generic

    token = secrets.token_urlsafe(24)
    biz.pos_setup_token = token
    db.session.commit()

    reset_url = f"{base_url.rstrip('/')}/pos/setup/{biz.slug}/{token}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1e293b; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0;">
      <h2 style="color: #15803d; margin-top: 0;">Restablecer PIN del POS</h2>
      <p>Hola,</p>
      <p>Recibimos una solicitud para restablecer el PIN de acceso al punto de venta (POS) para <strong>{biz.name}</strong>.</p>
      <p style="margin: 28px 0;">
        <a href="{reset_url}" style="background: #15803d; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; display: inline-block;">
          Crear nuevo PIN
        </a>
      </p>
      <p style="font-size: 0.9em; color: #64748b;">
        Si el botón no funciona, copia y pega este enlace en tu navegador:<br>
        <a href="{reset_url}" style="color: #15803d;">{reset_url}</a>
      </p>
      <p style="font-size: 0.85em; color: #94a3b8; margin-top: 24px; border-top: 1px solid #f1f5f9; padding-top: 12px;">
        Este enlace es de un solo uso. Si no solicitaste este cambio, puedes ignorar este mensaje.
      </p>
    </div>
    """
    text_body = f"Restablecer PIN del POS para {biz.name}\n\nIngresa al siguiente enlace para crear tu nuevo PIN:\n{reset_url}\n\nEste enlace es de un solo uso."

    send_email(
        to=user.email,
        subject=f"Restablecer PIN del POS · {biz.name}",
        html_body=html_body,
        text_body=text_body,
        sender_name="Velzia Verduras",
    )

    return True, msg_generic


def login_pos(identifier, pin, ip=None):
    """Autentica correo/teléfono/slug + PIN y deja la sesión del POS. Devuelve el Business."""
    identifier = str(identifier or '').strip()
    pin = str(pin or '').strip()
    business = find_business_by_identifier(identifier)
    if (business is None or business.vertical != 'verduras'
            or not business.is_active):
        raise PosAuthError('Correo, teléfono o PIN incorrecto')

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
        raise PosAuthError('Correo, teléfono o PIN incorrecto')

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

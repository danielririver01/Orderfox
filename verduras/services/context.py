"""
Contexto de tenant para el módulo Verduras.

PUNTO ÚNICO de contacto con core a nivel de DB: todo el módulo obtiene su
tenant a través de `get_business()` / `require_business()` en lugar de
consultar `Business` directamente. Cuando el módulo se extraiga a repo
propio, solo este archivo cambia (de SQLAlchemy directo a cliente HTTP de
la API de core) — el resto del módulo no se entera.

Contrato:
- Un Business es usable por este vertical si `is_active` y
  `vertical == 'verduras'`.
- Los Business con `vertical='restaurant'` existen en la misma tabla
  (espejos del puente) pero NO son tenants de este módulo.
"""
import re
from sqlalchemy import func
from app.models import Business, User, db


class BusinessNotFoundError(LookupError):
    """El business_id solicitado no existe."""


class BusinessNotVegetalError(ValueError):
    """El Business existe pero no pertenece al vertical 'verduras'."""


def get_business(business_id: int) -> Business | None:
    """Devuelve el Business por ID, o None si no existe."""
    return db.session.get(Business, business_id)


def get_business_by_slug(slug: str) -> Business | None:
    """Business por slug (login del POS: la URL amable del tendero)."""
    return Business.query.filter_by(slug=slug).first()


def find_business_by_identifier(identifier: str) -> Business | None:
    """Busca un Business del vertical 'verduras' por correo, teléfono o slug.

    Permite al tendero/dueño iniciar sesión usando su email de registro, su
    número de WhatsApp configurado, o el slug del negocio.
    """
    if not identifier:
        return None
    raw = str(identifier).strip()
    if not raw:
        return None

    # 1. Si contiene '@', buscar por correo del dueño (User.email)
    if '@' in raw:
        email_clean = raw.lower()
        user = User.query.filter(func.lower(User.email) == email_clean).first()
        if user:
            biz = Business.query.filter(
                Business.vertical == 'verduras',
                db.or_(
                    Business.owner_user_id == user.id,
                    Business.id == user.restaurant_id,
                ),
            ).first()
            if biz:
                return biz

    # 2. Si contiene dígitos, intentar coincidencia por teléfono
    phone_digits = re.sub(r'\D', '', raw)
    if len(phone_digits) >= 7:
        from verduras.models_sales import VerdurasBusinessSettings

        bizs = Business.query.filter(
            Business.vertical == 'verduras',
            Business.whatsapp_phone.isnot(None),
        ).all()
        for b in bizs:
            b_digits = re.sub(r'\D', '', b.whatsapp_phone or '')
            if b_digits and (b_digits == phone_digits or b_digits.endswith(phone_digits) or phone_digits.endswith(b_digits)):
                return b

        settings = VerdurasBusinessSettings.query.filter(
            VerdurasBusinessSettings.whatsapp_phone.isnot(None)
        ).all()
        for s in settings:
            s_digits = re.sub(r'\D', '', s.whatsapp_phone or '')
            if s_digits and (s_digits == phone_digits or s_digits.endswith(phone_digits) or phone_digits.endswith(s_digits)):
                biz = get_business(s.business_id)
                if biz and biz.vertical == 'verduras':
                    return biz

    # 3. Buscar por slug directo
    biz = Business.query.filter(
        Business.vertical == 'verduras',
        func.lower(Business.slug) == raw.lower(),
    ).first()
    if biz:
        return biz

    return None


def require_business(business_id: int) -> Business:
    """
    Devuelve el Business validado para este vertical, o levanta:
    - BusinessNotFoundError: no existe.
    - BusinessNotVegetalError: existe pero es otro vertical (p.ej. espejo
      de restaurante).
    """
    biz = get_business(business_id)
    if biz is None:
        raise BusinessNotFoundError(f"Business {business_id} no existe")
    if biz.vertical != 'verduras':
        raise BusinessNotVegetalError(
            f"Business {business_id} es vertical '{biz.vertical}', no 'verduras'"
        )
    if not biz.is_active:
        raise BusinessNotVegetalError(f"Business {business_id} está inactivo")
    return biz


def get_subscription_status(business: Business) -> dict:
    """Estado de suscripción del tenant — delegado 100% a core.

    La máquina de estados (trial → activo → gracia → vencido) vive en
    `app.utils.subscription.get_business_subscription_status`: el módulo no
    decide cuándo expira un plan, solo pregunta. Al extraer a repo propio,
    esto pasa a ser una llamada HTTP a core junto con el resto del contrato.
    """
    from app.utils.subscription import get_business_subscription_status
    return get_business_subscription_status(business)


class BusinessInactiveError(PermissionError):
    """Tenant legítimo pero sin suscripción usable (gracia/vencido)."""

    def __init__(self, status: dict):
        self.status = status
        super().__init__(status.get('message') or 'Suscripción inactiva')


def ensure_business_active(business: Business) -> None:
    """Valida que el tenant pueda operar HOY; levanta BusinessInactiveError."""
    status = get_subscription_status(business)
    if not status.get('can_crud'):
        raise BusinessInactiveError(status)


def list_verduras_businesses() -> list[Business]:
    """Businesses activos de este vertical (para directorio/dashboard)."""
    return (
        Business.query
        .filter_by(vertical='verduras', is_active=True)
        .order_by(Business.name)
        .all()
    )

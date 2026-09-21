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
from app.models import Business, db


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


def list_verduras_businesses() -> list[Business]:
    """Businesses activos de este vertical (para directorio/dashboard)."""
    return (
        Business.query
        .filter_by(vertical='verduras', is_active=True)
        .order_by(Business.name)
        .all()
    )

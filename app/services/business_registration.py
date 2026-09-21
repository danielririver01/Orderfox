"""
Registro self-service de verticales directos (verduras, ...) — Semana 6.

Diseño (decisión de producto acordada):
- UN solo funnel de registro, en core: /register/verduras (por ahora;
  luego un selector de vertical en la misma puerta). La suscripción, el
  trial y la cuenta User son cosas del SaaS — viven en core y NO se
  duplican por módulo.
- El módulo verduras jamás crea tenants: su contrato es "me llegan
  Businesses ya creados con vertical='verduras'" (lo valida require_business).
- El dueño tiene cuenta User de core (email+password, billing, Copilot VZ);
  el POS del tendero sigue usando slug+PIN del módulo (roles distintos).
- Reutiliza los patrones EXACTOS de AuthService: slug con RESERVED_SLUGS,
  trial único por email/teléfono (TrialHistory), welcome email no bloqueante.
- El token de setup del POS viaja en `businesses.pos_setup_token` (DB
  compartida = canal de integración del monorepo): el módulo lo consume,
  configura PIN + WhatsApp en SU tabla de settings y limpia el token.
"""
import re
import secrets
import unicodedata

from app.models import Business, User, db
from app.models.rewards import TrialHistory
from app.utils.constants import RESERVED_SLUGS

TRIAL_DAYS = 60


class BusinessRegistrationError(ValueError):
    """Registro rechazado (mensaje amable para el template)."""


def _clean_phone(phone) -> str:
    """Mantiene dígitos y '+' inicial (mismo criterio que el módulo)."""
    raw = str(phone or '').strip()
    cleaned = re.sub(r'[^\d+]', '', raw)
    return cleaned


def generate_and_ensure_slug(name: str) -> str:
    """Slug único para `businesses` — patrón AuthService.generate_slug."""
    text = unicodedata.normalize('NFKD', name or '')
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    base = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    if not base:
        raise BusinessRegistrationError(
            'El nombre del negocio no produce una dirección válida. '
            'Elige otro nombre.')
    if base in RESERVED_SLUGS:
        raise BusinessRegistrationError(
            f'El nombre "{name}" está reservado para el sistema. '
            'Elige uno más original para tu negocio.')
    slug, n = base, 2
    while Business.query.filter_by(slug=slug).first() is not None:
        slug = f'{base}-{n}'
        n += 1
    return slug


def check_trial_eligibility(email: str, whatsapp_phone: str):
    """Trial único por email o teléfono — MISMA regla que restaurantes.

    Reusa TrialHistory (misma tabla): el trial es del SaaS completo, no de
    un vertical — nadie lo cobra dos veces cambiando de vertical.
    """
    past = TrialHistory.query.filter(
        db.or_(TrialHistory.email == email,
               TrialHistory.whatsapp_phone == whatsapp_phone)
    ).first()
    if past:
        raise BusinessRegistrationError(
            'Este correo o número ya disfrutó de una prueba gratuita. '
            'Elige un plan de pago para continuar.')


def register_verduras_business(user: User, business_name: str,
                               whatsapp_phone: str, selected_plan: str):
    """Alta completa del tenant verduras: Business directo + trial + token.

    Devuelve (business, setup_token).
    Lanza BusinessRegistrationError ante plan/teléfono/trial inválidos.
    """
    if selected_plan not in ('trial', 'emprendedor', 'crecimiento', 'elite'):
        raise BusinessRegistrationError(f'Plan inválido: {selected_plan}')
    phone = _clean_phone(whatsapp_phone)
    if not 7 <= len(phone) <= 20:
        raise BusinessRegistrationError(
            'El WhatsApp del negocio no parece válido (usa formato '
            'internacional, ej: +573001112233).')
    if user.restaurant_id:
        raise BusinessRegistrationError(
            'Tu cuenta ya administra un restaurante. Usa esa sesión para '
            'operarlo.')

    is_trial = selected_plan == 'trial'
    if is_trial:
        check_trial_eligibility(user.email, phone)

    slug = generate_and_ensure_slug(business_name)

    business = Business.create_direct_vertical(
        vertical='verduras',
        name=business_name.strip(),
        slug=slug,
        owner_user_id=user.id,
        plan_type=selected_plan,
        trial_days=TRIAL_DAYS,
    )

    if is_trial:
        db.session.add(TrialHistory(email=user.email, whatsapp_phone=phone))

    # Token de UN SOLO USO para el setup del POS en el módulo (PIN +
    # WhatsApp). Consumido por verduras/services/pos_auth.consume_setup_token.
    setup_token = secrets.token_urlsafe(24)
    business.pos_setup_token = setup_token
    db.session.commit()
    return business, setup_token

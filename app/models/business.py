"""
Business — raíz del tenant multi-vertical (puente expand-contract).

Estrategia (rama feature/verduras, ver CHANGELOG):
- La tabla `businesses` alinea sus IDs con `restaurants` (b.id == r.id),
  así las FKs `restaurant_id` existentes siguen válidas SIN migración masiva.
- Los listeners ORM de este módulo mantienen el invariante 1:1:
  crear/actualizar/borrar un Restaurant se refleja en `businesses`.
- Código nuevo (módulo verduras y futuros verticales) usa `Business`
  y `business_id` directamente, nunca FKs nuevas hacia `restaurants`.

⚠️ Gotchas (documentados en AGENTS.md):
- UPDATE/DELETE por SQL crudo sobre `restaurants` bypassa el puente.
- Este módulo se importa desde app/models/__init__.py para que los
  listeners queden registrados siempre.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from app.models import db
from app.models.core import AwareDateTime, Restaurant

# Banda de IDs reservada para Businesses de verticales creados DIRECTAMENTE
# (sin Restaurant espejo: verduras, delivery, farmacia, etc.). Los espejos de
# restaurantes usan el ID real de `restaurants` (autoincrement < 1M), así
# ambas poblaciones nunca chocan en la PK compartida.
DIRECT_VERTICAL_ID_FLOOR = 1_000_000


class Business(db.Model):
    """
    Raíz del tenant multi-vertical: una cuenta (negocio) con un `vertical`.

    Para los negocios de restaurante existe una fila espejo con EL MISMO ID
    (creada automáticamente por los listeners de este módulo). Los verticales
    nuevos (verduras, delivery, etc.) crean `Business` directamente con
    autoincrement.
    """
    __tablename__ = 'businesses'

    id = db.Column(db.Integer, primary_key=True)
    # Vertical activo: 'restaurant' | 'verduras' | ... (futuros: delivery,
    # farmacia, ...)
    vertical = db.Column(db.String(30), default='restaurant',
                         server_default='restaurant', nullable=False)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False,
                          server_default='1')
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc),
                           server_default='CURRENT_TIMESTAMP')

    # ── Registro self-service multi-vertical (Semana 6 / v0.8.0) ──
    # Dueño: cuenta User de core (billing, Copilot VZ). Los espejos de
    # restaurantes quedan NULL (el dueño ahí es User.restaurant_id, igual
    # que siempre — backward-compatible).
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True, index=True)
    # Suscripción a nivel tenant (los verticales directos NO tienen fila en
    # `restaurants`; si no viviera aquí, quedarían fuera de todo el ciclo
    # trial → activo → grace → dormant). Planes: mismos valores de core.
    plan_type = db.Column(db.String(20), default='trial', nullable=False,
                          server_default='trial')
    subscription_expires_at = db.Column(AwareDateTime, nullable=True)
    # Ciclo de vida SaaS del Business (vertical directo): 'active' | 'dormant'
    # | 'cancellation_pending' — misma semántica que en Restaurant.
    subscription_state = db.Column(
        db.String(20), default='active', server_default='active',
        nullable=False)
    # Momento del dormido (scheduler de lifecycle) — misma auditoría que
    # Restaurant.dormant_at: preservar datos, nunca borrarlos.
    dormant_at = db.Column(AwareDateTime, nullable=True)
    has_used_trial = db.Column(db.Boolean, default=False, nullable=False,
                               server_default='0')
    # WhatsApp dado en el registro de core (una sola vez): el setup del POS
    # lo trae pre-llenado (editable). NULL = no dado / espejos viejos.
    whatsapp_phone = db.Column(db.String(20), nullable=True)
    # Token de UN SOLO USO para el setup del POS del módulo (PIN + WhatsApp).
    # Core lo emite al registrar; el módulo lo consume (comparación en tiempo
    # constante) y lo limpia — vía la DB compartida, el canal de integración
    # de la arquitectura. NULL = sin setup pendiente.
    pos_setup_token = db.Column(db.String(64), nullable=True)
    # Handoff Mundos → POS: token de UN SOLO USO con expiración corta para
    # que el dueño salte de su dashboard (core) al POS del módulo (5100)
    # sin re-loguearse. Core lo emite, el módulo lo consume y lo limpia.
    # Solo un token vivo a la vez: mintear reemplaza el anterior.
    # NULL = sin handoff pendiente.
    pos_sso_token = db.Column(db.String(64), nullable=True)
    pos_sso_expires_at = db.Column(AwareDateTime, nullable=True)

    # Perfil del vertical restaurante: fila de `restaurants` con el mismo ID.
    # Solo lectura — la escritura vive en los listeners (mismo ID, sin FK).
    restaurant_profile = db.relationship(
        'Restaurant',
        primaryjoin='foreign(Restaurant.id) == Business.id',
        viewonly=True,
        uselist=False,
    )

    def __repr__(self):
        return f'<Business {self.slug} ({self.vertical})>'

    @classmethod
    def create_direct(cls, vertical, name, slug, is_active=True):
        """
        Crea un Business de un vertical NO-restaurante (sin Restaurant espejo).

        Usa la banda reservada de IDs (>= DIRECT_VERTICAL_ID_FLOOR) para no
        colisionar con los espejos creados desde `restaurants`.

        ⚠️ MAX(id)+1 es susceptible de carrera bajo alta concurrencia; a la
        escala actual es aceptable y la PK única falla ruidosamente (no
        corrompe datos). Si algún día hay escritura concurrente real de
        verticales, migrar a un sequence/table aparte.
        """
        if vertical == 'restaurant':
            raise ValueError(
                "Verticales 'restaurant' deben nacer como Restaurant (espejo "
                "automático); no usar create_direct()."
            )
        max_id = db.session.query(db.func.max(cls.id)).scalar() or 0
        next_id = max(max_id + 1, DIRECT_VERTICAL_ID_FLOOR)
        biz = cls(id=next_id, vertical=vertical, name=name, slug=slug,
                  is_active=is_active)
        db.session.add(biz)
        db.session.flush()
        return biz

    @classmethod
    def create_direct_vertical(cls, vertical, name, slug, owner_user_id,
                               plan_type='trial', trial_days=60):
        """Registro self-service de un vertical directo (verduras, ...).

        Añade sobre create_direct(): dueño (User de core), plan y trial.
        - trial: is_active=True por 60 días + marca has_used_trial (mismo
          comportamiento que el trial de restaurantes).
        - plan pago: is_active=False hasta registrar el pago (mismo patrón
          que create_restaurant_from_setup → /payment).
        """
        if plan_type == 'trial':
            biz = cls.create_direct(
                vertical=vertical, name=name, slug=slug, is_active=True)
            biz.subscription_expires_at = (
                datetime.now(timezone.utc) + timedelta(days=trial_days))
            biz.has_used_trial = True
        else:
            biz = cls.create_direct(
                vertical=vertical, name=name, slug=slug, is_active=False)
        biz.owner_user_id = owner_user_id
        biz.plan_type = plan_type
        db.session.flush()
        return biz


# ── Listeners del puente Restaurant ↔ Business ──────────────
# Usan la connection del flush (mismo commit/rollback, sin sesión anidada).


@event.listens_for(Restaurant, 'after_insert')
def create_business_for_restaurant(mapper, connection, target):
    """Todo Restaurant nuevo nace con su Business espejo (mismo ID)."""
    connection.execute(
        Business.__table__.insert().values(
            id=target.id,
            vertical='restaurant',
            name=target.name,
            slug=target.slug,
            is_active=bool(target.is_active),
        )
    )


@event.listens_for(Restaurant, 'before_update')
def sync_business_on_restaurant_update(mapper, connection, target):
    """Renombrar/desactivar un restaurante se refleja en su Business."""
    connection.execute(
        Business.__table__.update()
        .where(Business.__table__.c.id == target.id)
        .values(
            name=target.name,
            slug=target.slug,
            is_active=bool(target.is_active),
            updated_at=datetime.now(timezone.utc),
        )
    )


@event.listens_for(Restaurant, 'before_delete')
def delete_business_before_restaurant(mapper, connection, target):
    """Borrar el restaurante borra su fila espejo (sin FK, puente manual)."""
    connection.execute(
        Business.__table__.delete()
        .where(Business.__table__.c.id == target.id)
    )

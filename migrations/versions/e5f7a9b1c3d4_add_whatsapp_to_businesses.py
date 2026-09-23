"""add whatsapp_phone to businesses (single ask in core, prefill in module)

Revision ID: e5f7a9b1c3d4
Revises: d4e6f8a0b2c3
Create Date: 2026-09-21

El registro de core (/register/verduras) pedía WhatsApp solo para el
chequeo de trial y lo descartaba; el setup del POS lo volvía a pedir.
Ahora core lo GUARDA en el Business (DB compartida = canal del monorepo)
y el setup del módulo lo trae pre-llenado (editable, por si el número del
mostrador es otro). Nullable, sin backfill: los existentes quedan NULL y
el setup muestra el campo vacío como siempre.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f7a9b1c3d4'
down_revision = 'd4e6f8a0b2c3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('businesses')}

    if 'whatsapp_phone' not in cols:
        op.add_column(
            'businesses',
            sa.Column('whatsapp_phone', sa.String(length=20), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('businesses')}

    if 'whatsapp_phone' in cols:
        op.drop_column('businesses', 'whatsapp_phone')

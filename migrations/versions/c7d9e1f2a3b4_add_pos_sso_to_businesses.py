"""add pos_sso_token + pos_sso_expires_at to businesses (handoff Mundos->POS)

Revision ID: c7d9e1f2a3b4
Revises: b6d8f0a2c4e6
Create Date: 2026-09-22

El dueño hace clic en su mundo (Verdurería) en el dashboard de core y debe
entrar al POS del módulo (puerto 5100) sin escribir el PIN de mostrador.
Core emite un token de un solo uso con expiración corta; el módulo lo
consume (comparación en tiempo constante) y lo limpia. Mismo canal que
`pos_setup_token`: la DB compartida del monorepo.

Nullable, sin backfill: los existentes quedan NULL (= sin handoff).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d9e1f2a3b4'
down_revision = 'b6d8f0a2c4e6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('businesses')}

    if 'pos_sso_token' not in cols:
        op.add_column(
            'businesses',
            sa.Column('pos_sso_token', sa.String(length=64), nullable=True),
        )
    if 'pos_sso_expires_at' not in cols:
        op.add_column(
            'businesses',
            sa.Column('pos_sso_expires_at', sa.DateTime(timezone=True),
                      nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('businesses')}

    if 'pos_sso_expires_at' in cols:
        op.drop_column('businesses', 'pos_sso_expires_at')
    if 'pos_sso_token' in cols:
        op.drop_column('businesses', 'pos_sso_token')

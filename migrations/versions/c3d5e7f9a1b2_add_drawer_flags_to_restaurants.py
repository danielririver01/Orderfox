"""add drawer flags to restaurants (physical cash drawer via QZ Tray)

Revision ID: c3d5e7f9a1b2
Revises: b2e4c6a8d0f2
Create Date: 2026-09-21

Cajón físico (QZ Tray, puente local en el PC del mostrador):
- `drawer_enabled`: el local declaró cajón+impresora DK y QZ instalado.
- `drawer_auto_open`: abrir solo al cobrar en efectivo.
Ambos default False (string '0', convención del repo para boolean en
Postgres): sin hardware todo funciona igual que siempre.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c3d5e7f9a1b2'
down_revision = 'b2e4c6a8d0f2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('restaurants')}

    if 'drawer_enabled' not in cols:
        op.add_column(
            'restaurants',
            sa.Column('drawer_enabled', sa.Boolean(), nullable=False,
                      server_default='0'),
        )
    if 'drawer_auto_open' not in cols:
        op.add_column(
            'restaurants',
            sa.Column('drawer_auto_open', sa.Boolean(), nullable=False,
                      server_default='0'),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('restaurants')}

    if 'drawer_auto_open' in cols:
        op.drop_column('restaurants', 'drawer_auto_open')
    if 'drawer_enabled' in cols:
        op.drop_column('restaurants', 'drawer_enabled')

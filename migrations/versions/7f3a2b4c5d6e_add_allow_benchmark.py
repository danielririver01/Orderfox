"""add allow_benchmark to restaurants

Revision ID: 7f3a2b4c5d6e
Revises: e677a1b1babc
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa

revision = '7f3a2b4c5d6e'
down_revision = 'e677a1b1babc'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('restaurants',
        sa.Column('allow_benchmark', sa.Boolean(),
                  server_default='0', nullable=False))
    # Consentimiento expreso: todos los restaurantes existentes quedan en False
    # hasta que el usuario active explícitamente el benchmarking.
    op.execute('UPDATE restaurants SET allow_benchmark = 0')


def downgrade():
    op.drop_column('restaurants', 'allow_benchmark')

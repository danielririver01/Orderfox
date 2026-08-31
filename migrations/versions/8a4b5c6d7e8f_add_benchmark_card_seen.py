"""add benchmark_card_seen to restaurants

Revision ID: 8a4b5c6d7e8f
Revises: 7f3a2b4c5d6e
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa

revision = '8a4b5c6d7e8f'
down_revision = '7f3a2b4c5d6e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('restaurants',
        sa.Column('benchmark_card_seen', sa.Boolean(),
                  server_default='0', nullable=False))


def downgrade():
    op.drop_column('restaurants', 'benchmark_card_seen')

"""revert benchmark to opt-out, drop benchmark_card_seen

Revision ID: 9b0c1d2e3f4a
Revises: 8a4b5c6d7e8f
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa

revision = '9b0c1d2e3f4a'
down_revision = '8a4b5c6d7e8f'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('UPDATE restaurants SET allow_benchmark = true')
    op.execute("ALTER TABLE restaurants ALTER COLUMN allow_benchmark SET DEFAULT true")
    op.execute("ALTER TABLE restaurants ALTER COLUMN allow_benchmark SET NOT NULL")
    op.drop_column('restaurants', 'benchmark_card_seen')


def downgrade():
    op.add_column('restaurants',
        sa.Column('benchmark_card_seen', sa.Boolean(),
                  server_default='0', nullable=False))
    op.execute('UPDATE restaurants SET allow_benchmark = false')
    op.alter_column('restaurants', 'allow_benchmark',
                     server_default='0', nullable=False)

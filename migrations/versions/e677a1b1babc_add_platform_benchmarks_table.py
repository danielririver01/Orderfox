"""add platform_benchmarks table

Revision ID: e677a1b1babc
Revises: 6ada7cfd926d
Create Date: 2026-08-25 15:42:22.440749

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e677a1b1babc'
down_revision = '6ada7cfd926d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('platform_benchmarks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cohort', sa.String(length=30), nullable=False),
    sa.Column('restaurant_count', sa.Integer(), nullable=False),
    sa.Column('period_days', sa.Integer(), nullable=False),
    sa.Column('metrics_json', sa.Text(), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('platform_benchmarks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_platform_benchmarks_cohort'), ['cohort'], unique=True)


def downgrade():
    with op.batch_alter_table('platform_benchmarks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_platform_benchmarks_cohort'))

    op.drop_table('platform_benchmarks')

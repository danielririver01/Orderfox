"""add order events table

Revision ID: a1b2c3d4e5f6
Revises: bb7664a99a86
Create Date: 2026-08-18 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

from app.models.core import AwareDateTime

# revision identifiers, used by Alembic.
revision = '7c5dc42affdd'
down_revision = 'bb7664a99a86'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'order_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_role', sa.String(length=20), nullable=True),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', AwareDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_events_order_id'), 'order_events', ['order_id'], unique=False)


def downgrade():
    op.drop_table('order_events')
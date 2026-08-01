"""add copilot_business_events

Revision ID: c9d4e5f6a7b8
Revises: e1416d521288
Create Date: 2026-08-01 18:20:00.000000

La tabla se creaba antes con un patch SQL manual (migrations/raw_add_business_events.sql)
que nunca se aplico en todas las bases. Esta migracion es idempotente para cubrir
entornos donde la tabla ya existe (via raw SQL) y no fallar en `flask db upgrade`.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c9d4e5f6a7b8'
down_revision = 'e1416d521288'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.has_table(bind, 'copilot_business_events'):
        return
    op.create_table(
        'copilot_business_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.SmallInteger(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('preview', sa.String(length=300), nullable=False),
        sa.Column('template_key', sa.String(length=50), nullable=False),
        sa.Column('template_data', sa.Text(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['copilot_conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_copilot_business_events_restaurant_id', 'copilot_business_events', ['restaurant_id'])
    op.create_index('ix_copilot_business_events_kind', 'copilot_business_events', ['kind'])
    op.create_index('ix_copilot_business_events_priority', 'copilot_business_events', ['priority'])
    op.create_index('ix_copilot_business_events_active', 'copilot_business_events', ['active'])


def downgrade():
    op.drop_index('ix_copilot_business_events_active', table_name='copilot_business_events')
    op.drop_index('ix_copilot_business_events_priority', table_name='copilot_business_events')
    op.drop_index('ix_copilot_business_events_kind', table_name='copilot_business_events')
    op.drop_index('ix_copilot_business_events_restaurant_id', table_name='copilot_business_events')
    op.drop_table('copilot_business_events')

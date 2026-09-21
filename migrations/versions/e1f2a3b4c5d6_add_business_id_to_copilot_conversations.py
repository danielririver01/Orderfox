"""add business_id to copilot_conversations (Copilot multi-vertical FASE 0)

Revision ID: e1f2a3b4c5d6
Revises: a1f6e3d2b4c5
Create Date: 2026-09-21

Expand (backward-compatible, sin backfill):
- Nueva columna nullable business_id → businesses.id (tenants directos como
  verdulería, sin espejo en restaurants).
- restaurant_id pasa a nullable (antes NOT NULL): las conversaciones de
  restaurante siguen usándolo; las de verticales usan business_id.
- Sin UPDATE/DELETE de datos existentes: las filas actuales quedan intactas.
"""
import sqlalchemy as sa
from alembic import op

revision = 'e1f2a3b4c5d6'
down_revision = 'a1f6e3d2b4c5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'copilot_conversations',
        sa.Column('business_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_copilot_conversations_business_id',
        'copilot_conversations', 'businesses',
        ['business_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index(
        'ix_copilot_conversations_business_id',
        'copilot_conversations', ['business_id'], unique=False,
    )
    op.alter_column(
        'copilot_conversations', 'restaurant_id',
        existing_type=sa.Integer(), nullable=True,
    )


def downgrade():
    op.alter_column(
        'copilot_conversations', 'restaurant_id',
        existing_type=sa.Integer(), nullable=False,
    )
    op.drop_index('ix_copilot_conversations_business_id',
                  table_name='copilot_conversations')
    op.drop_constraint('fk_copilot_conversations_business_id',
                       'copilot_conversations', type_='foreignkey')
    op.drop_column('copilot_conversations', 'business_id')

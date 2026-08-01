"""add reward_claims table for Sorpresa Velzia

Revision ID: d7e8f9a0b1c2
Revises: a4b2c3d4e5f6
Create Date: 2026-07-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'd7e8f9a0b1c2'
down_revision = 'a4b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reward_claims',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=36), nullable=False),
        sa.Column('plan_key', sa.String(length=50), nullable=False),
        sa.Column('rarity', sa.String(length=20), nullable=False),
        sa.Column('reward_type', sa.String(length=50), nullable=False),
        sa.Column('reward_value', sa.Integer(), nullable=True),
        sa.Column('reward_label', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_reward_claims_user_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_reward_claims_restaurant_id'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_reward_claims_token'), 'reward_claims', ['token'], unique=True)
    op.create_index(op.f('ix_reward_claims_user_id'), 'reward_claims', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_reward_claims_user_id'), table_name='reward_claims')
    op.drop_index(op.f('ix_reward_claims_token'), table_name='reward_claims')
    op.drop_table('reward_claims')

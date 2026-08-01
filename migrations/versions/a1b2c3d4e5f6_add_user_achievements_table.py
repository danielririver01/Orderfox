"""add user_achievements table

Revision ID: a1b2c3d4e5f6
Revises: e4b30b77e164
Create Date: 2026-07-25 13:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e4b30b77e164'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user_achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('achievement_id', sa.String(length=50), nullable=False, index=True),
        sa.Column('current_progress', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('required_progress', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('earned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )


def downgrade():
    op.drop_table('user_achievements')

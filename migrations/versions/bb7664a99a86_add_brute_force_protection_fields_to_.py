"""add brute force protection fields to users

Revision ID: bb7664a99a86
Revises: f9e2a1b3c4d5
Create Date: 2026-08-17 15:48:03.238801

"""
from alembic import op
import sqlalchemy as sa
from app.models.core import AwareDateTime

# revision identifiers, used by Alembic.
revision = 'bb7664a99a86'
down_revision = 'f9e2a1b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_pin_attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('locked_until', AwareDateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_pin_attempts')

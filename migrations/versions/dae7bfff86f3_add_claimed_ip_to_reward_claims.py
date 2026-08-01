"""add claimed_ip to reward_claims

Revision ID: dae7bfff86f3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-25 13:03:06.068491

"""
from alembic import op
import sqlalchemy as sa


revision = 'dae7bfff86f3'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reward_claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('claimed_ip', sa.String(length=45), nullable=True))


def downgrade():
    with op.batch_alter_table('reward_claims', schema=None) as batch_op:
        batch_op.drop_column('claimed_ip')

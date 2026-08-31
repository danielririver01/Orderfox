"""add subscription lifecycle fields

Revision ID: c4c47adbb493
Revises: 7c5dc42affdd
Create Date: 2026-08-22 10:02:09.152237

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4c47adbb493'
down_revision = '7c5dc42affdd'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('subscription_state', sa.String(length=20), nullable=False, server_default='active')
        )
        # AwareDateTime se guarda como DATETIME con timezone en MySQL
        batch_op.add_column(
            sa.Column('dormant_at', sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('dormant_at')
        batch_op.drop_column('subscription_state')

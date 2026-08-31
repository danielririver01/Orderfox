"""add cancellation_requested_at column

Revision ID: 6ada7cfd926d
Revises: c4c47adbb493
Create Date: 2026-08-22 11:30:28.448574

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6ada7cfd926d'
down_revision = 'c4c47adbb493'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cancellation_requested_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('cancellation_requested_at')

"""add auto-photo columns to products

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f7
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_source', sa.String(length=30), nullable=True))
        batch_op.add_column(
            sa.Column('is_auto_image', sa.Boolean(), nullable=False, server_default='0')
        )
        batch_op.add_column(sa.Column('suggested_image_pool', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('suggested_image_pool')
        batch_op.drop_column('is_auto_image')
        batch_op.drop_column('image_source')

"""add unsplash_source_url to products

Revision ID: a1b2c3d4e5f7
Revises: 9b0c1d2e3f4a
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = '9b0c1d2e3f4a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('unsplash_source_url', sa.Text(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('unsplash_source_url')

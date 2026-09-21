"""add min_stock to verduras_products (rotation alerts)

Revision ID: d9c4e2a6b8f1
Revises: f3b8d2c4e6a1
Create Date: 2026-09-21

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd9c4e2a6b8f1'
down_revision = 'f3b8d2c4e6a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """add min_stock (nullable, opt-in threshold) to verduras_products"""
    with op.batch_alter_table('verduras_products') as batch_op:
        batch_op.add_column(
            sa.Column('min_stock', sa.Numeric(precision=12, scale=3),
                      nullable=True))


def downgrade() -> None:
    """remove min_stock column"""
    with op.batch_alter_table('verduras_products') as batch_op:
        batch_op.drop_column('min_stock')

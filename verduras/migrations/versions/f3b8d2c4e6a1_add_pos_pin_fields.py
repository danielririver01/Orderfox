"""add pos pin fields to verduras_business_settings

Revision ID: f3b8d2c4e6a1
Revises: e7a9c1d3f5b2
Create Date: 2026-09-21

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f3b8d2c4e6a1'
down_revision = 'e7a9c1d3f5b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """add pos pin fields to verduras_business_settings"""
    with op.batch_alter_table('verduras_business_settings',
                              schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('pos_pin_hash', sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column('pos_pin_updated_at',
                      sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """drop pos pin fields from verduras_business_settings"""
    with op.batch_alter_table('verduras_business_settings',
                              schema=None) as batch_op:
        batch_op.drop_column('pos_pin_updated_at')
        batch_op.drop_column('pos_pin_hash')

"""add verduras inventory tables (lots, merma)

Revision ID: e7a9c1d3f5b2
Revises: b8d2e4f6a9c1
Create Date: 2026-09-21

"""
import sqlalchemy as sa
from alembic import op

import app.models.core

# revision identifiers, used by Alembic.
revision = 'e7a9c1d3f5b2'
down_revision = 'b8d2e4f6a9c1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """add verduras inventory tables"""
    op.create_table('verduras_lots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('purchased_at', app.models.core.AwareDateTime(timezone=True), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', app.models.core.AwareDateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['verduras_products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('verduras_lots', schema=None) as batch_op:
        batch_op.create_index('ix_verduras_lots_business_product', ['business_id', 'product_id'], unique=False)

    op.create_table('verduras_merma',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
    sa.Column('reason', sa.String(length=20), server_default='danado', nullable=False),
    sa.Column('cost_loss', sa.Numeric(12, 2), nullable=False),
    sa.Column('registered_at', app.models.core.AwareDateTime(timezone=True), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['verduras_products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('verduras_merma', schema=None) as batch_op:
        batch_op.create_index('ix_verduras_merma_business_product', ['business_id', 'product_id'], unique=False)
        batch_op.create_index('ix_verduras_merma_registered', ['business_id', 'registered_at'], unique=False)


def downgrade() -> None:
    """drop verduras inventory tables"""
    with op.batch_alter_table('verduras_merma', schema=None) as batch_op:
        batch_op.drop_index('ix_verduras_merma_registered')
        batch_op.drop_index('ix_verduras_merma_business_product')
    op.drop_table('verduras_merma')
    with op.batch_alter_table('verduras_lots', schema=None) as batch_op:
        batch_op.drop_index('ix_verduras_lots_business_product')
    op.drop_table('verduras_lots')

"""add verduras sales tables (settings, sales, sale_items, counters)

Revision ID: b8d2e4f6a9c1
Revises: 3fdc7c9baadf
Create Date: 2026-09-21

"""
import sqlalchemy as sa
from alembic import op

import app.models.core

# revision identifiers, used by Alembic.
revision = 'b8d2e4f6a9c1'
down_revision = '3fdc7c9baadf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """add verduras sales tables"""
    op.create_table('verduras_business_settings',
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('whatsapp_phone', sa.String(length=20), nullable=True),
    sa.Column('is_open', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('delivery_enabled', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('updated_at', app.models.core.AwareDateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
    sa.PrimaryKeyConstraint('business_id')
    )

    op.create_table('verduras_sales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('sale_number', sa.String(length=20), nullable=False),
    sa.Column('customer_name', sa.String(length=80), server_default='', nullable=False),
    sa.Column('customer_phone', sa.String(length=20), server_default='', nullable=False),
    sa.Column('sale_type', sa.String(length=15), server_default='walk_in', nullable=False),
    sa.Column('delivery_address', sa.String(length=200), nullable=True),
    sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('status', sa.String(length=15), server_default='pending', nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('created_at', app.models.core.AwareDateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('completed_at', app.models.core.AwareDateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', app.models.core.AwareDateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'idempotency_key', name='uq_verduras_sales_business_idem')
    )
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.create_index('ix_verduras_sales_business', ['business_id'], unique=False)

    op.create_table('verduras_sale_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('product_name', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=10), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=10, scale=3), nullable=False),
    sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['verduras_products.id'], ),
    sa.ForeignKeyConstraint(['sale_id'], ['verduras_sales.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('verduras_sale_items', schema=None) as batch_op:
        batch_op.create_index('ix_verduras_sale_items_sale', ['sale_id'], unique=False)

    op.create_table('verduras_sale_counters',
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('last_number', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
    sa.PrimaryKeyConstraint('business_id', 'date', name='pk_verduras_sale_counters')
    )


def downgrade() -> None:
    """drop verduras sales tables"""
    op.drop_table('verduras_sale_counters')
    with op.batch_alter_table('verduras_sale_items', schema=None) as batch_op:
        batch_op.drop_index('ix_verduras_sale_items_sale')
    op.drop_table('verduras_sale_items')
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.drop_index('ix_verduras_sales_business')
    op.drop_table('verduras_sales')
    op.drop_table('verduras_business_settings')

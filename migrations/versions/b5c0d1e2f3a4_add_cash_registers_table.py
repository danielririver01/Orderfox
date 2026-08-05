"""add cash_registers table and orders(restaurant_id, paid_at) index

Revision ID: b5c0d1e2f3a4
Revises: f3e7d1a2b9c0
Create Date: 2026-08-03 16:30:00.000000

Centro de Caja: tabla de cierres persistentes + índice para consultas por
`paid_at` (los totales de caja se basan en `paid_at`, no en `created_at`).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b5c0d1e2f3a4'
down_revision = 'f3e7d1a2b9c0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {t for t in inspector.get_table_names()}

    if 'cash_registers' not in tables:
        op.create_table(
            'cash_registers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('restaurant_id', sa.Integer(),
                      sa.ForeignKey('restaurants.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('closed_by', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'),
                      nullable=True),
            sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
            sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
            sa.Column('total_sales', sa.Integer(), nullable=False, default=0),
            sa.Column('total_orders', sa.Integer(), nullable=False, default=0),
            sa.Column('avg_ticket', sa.Integer(), nullable=False, default=0),
            sa.Column('cash_total', sa.Integer(), nullable=False, default=0),
            sa.Column('cash_orders', sa.Integer(), nullable=False, default=0),
            sa.Column('nequi_total', sa.Integer(), nullable=False, default=0),
            sa.Column('nequi_orders', sa.Integer(), nullable=False, default=0),
            sa.Column('bancolombia_total', sa.Integer(), nullable=False, default=0),
            sa.Column('bancolombia_orders', sa.Integer(), nullable=False, default=0),
            sa.Column('card_total', sa.Integer(), nullable=False, default=0),
            sa.Column('card_orders', sa.Integer(), nullable=False, default=0),
            sa.Column('cash_change_total', sa.Integer(), nullable=False, default=0),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint('restaurant_id', 'period_start',
                                name='uq_restaurant_period_start'),
        )

    # Índice para las consultas del Centro de Caja por rango de paid_at.
    idx_name = 'ix_orders_restaurant_paid_at'
    order_indexes = {ix['name'] for ix in inspector.get_indexes('orders')}
    if idx_name not in order_indexes:
        op.create_index(idx_name, 'orders', ['restaurant_id', 'paid_at'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {t for t in inspector.get_table_names()}

    if 'cash_registers' in tables:
        op.drop_table('cash_registers')

    order_indexes = {ix['name'] for ix in inspector.get_indexes('orders')}
    if 'ix_orders_restaurant_paid_at' in order_indexes:
        op.drop_index('ix_orders_restaurant_paid_at', table_name='orders')

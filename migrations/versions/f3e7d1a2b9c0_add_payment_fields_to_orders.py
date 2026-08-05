"""add payment fields to orders (payment_method, amount_received, change_due, paid_at)

Revision ID: f3e7d1a2b9c0
Revises: c9d4e5f6a7b8
Create Date: 2026-08-03 12:30:00.000000

Modal de pago / caja registradora. Agrega los campos de pago a la tabla
`orders` de forma idempotente para no fallar si las columnas ya existen
en algún entorno donde se aplicó manualmente.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f3e7d1a2b9c0'
down_revision = 'c9d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('orders')}

    if 'payment_method' not in columns:
        op.add_column('orders', sa.Column('payment_method', sa.String(length=20), nullable=True))
    if 'amount_received' not in columns:
        op.add_column('orders', sa.Column('amount_received', sa.Integer(), nullable=True))
    if 'change_due' not in columns:
        op.add_column('orders', sa.Column('change_due', sa.Integer(), nullable=True))
    if 'paid_at' not in columns:
        op.add_column('orders', sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('orders')}

    for col in ('paid_at', 'change_due', 'amount_received', 'payment_method'):
        if col in columns:
            op.drop_column('orders', col)

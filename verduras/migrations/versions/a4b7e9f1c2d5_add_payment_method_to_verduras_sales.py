"""add payment_method to verduras_sales (POS redisenado v1)

Revision ID: a4b7e9f1c2d5
Revises: d9c4e2a6b8f1
Create Date: 2026-09-22

El ticket del POS guarda el metodo de pago desde el dia 1 (el Copilot VZ
lo necesitara para "60% efectivo, 40% transferencia"). Nullable, sin
backfill: las ventas viejas quedan NULL (= sin dato, se pintan sin metodo).
"libreta" es etiqueta en v1, sin ledger (llega con Clientes/Fiados).
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a4b7e9f1c2d5'
down_revision = 'd9c4e2a6b8f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """add payment_method to verduras_sales"""
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('payment_method', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """drop payment_method from verduras_sales"""
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.drop_column('payment_method')

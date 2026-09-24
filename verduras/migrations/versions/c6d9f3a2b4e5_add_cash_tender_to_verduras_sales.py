"""add amount_received + change_due to verduras_sales (control de caja)

Revision ID: c6d9f3a2b4e5
Revises: b5c8e2f4a1d3
Create Date: 2026-09-23

El efectivo se registraba "a ciegas": sin lo recibido no hay forma de
saber si faltó o sobró al cuadrar. Nullable, sin backfill: ventas viejas
quedan NULL (= sin control de recibido, como antes).
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c6d9f3a2b4e5'
down_revision = 'b5c8e2f4a1d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('amount_received', sa.Numeric(precision=12, scale=2),
                      nullable=True))
        batch_op.add_column(
            sa.Column('change_due', sa.Numeric(precision=12, scale=2),
                      nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.drop_column('change_due')
        batch_op.drop_column('amount_received')

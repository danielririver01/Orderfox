"""fiados v2: credit_limit + internal_note en clientes, method en abonos

Revision ID: a1b2c3d4e5f6
Revises: f9a2b5c8d1e4
Create Date: 2026-09-24

Rediseño de Clientes/Fiados (diseño Stitch): la libreta gana cupo de
crédito (NULL = sin límite, compatibilidad total), nota interna del
tendero y el abono registra su método de pago (NULL = viejos sin dato).
Columnas NULLables: cero backfill, las cuentas viejas siguen igual.
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f9a2b5c8d1e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('verduras_clientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'credit_limit', sa.Numeric(precision=12, scale=2),
            nullable=True))
        batch_op.add_column(sa.Column(
            'internal_note', sa.String(length=500), nullable=True))
    with op.batch_alter_table('verduras_abonos', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'method', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('verduras_abonos', schema=None) as batch_op:
        batch_op.drop_column('method')
    with op.batch_alter_table('verduras_clientes', schema=None) as batch_op:
        batch_op.drop_column('internal_note')
        batch_op.drop_column('credit_limit')

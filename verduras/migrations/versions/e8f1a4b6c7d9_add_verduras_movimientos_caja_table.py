"""add verduras_movimientos_caja table (libro de caja mínimo)

Revision ID: e8f1a4b6c7d9
Revises: d7e0f4b3c5a6
Create Date: 2026-09-24

Ingresos/retiros fuera de ventas (fondo de mañana, salida al mercado).
Entran al esperado del cierre: efectivo + ingresos − retiros. Sin turnos
en v1: van atados al día operativo (Bogotá).
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e8f1a4b6c7d9'
down_revision = 'd7e0f4b3c5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'verduras_movimientos_caja',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2),
                  nullable=False),
        sa.Column('motivo', sa.String(length=120), nullable=True),
        sa.Column('registered_at', sa.DateTime(timezone=True),
                  nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_verduras_movimientos_business_day',
                    'verduras_movimientos_caja', ['business_id', 'day'])


def downgrade() -> None:
    op.drop_index('ix_verduras_movimientos_business_day',
                  table_name='verduras_movimientos_caja')
    op.drop_table('verduras_movimientos_caja')

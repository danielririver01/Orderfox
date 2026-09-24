"""add verduras_cierres table (cierre Z del día)

Revision ID: d7e0f4b3c5a6
Revises: c6d9f3a2b4e5
Create Date: 2026-09-23

Cierre Final Z v1 (sin turnos): un registro por día y negocio con snapshot
de ventas + conteo físico del cajón + diferencia calculada. Unique en
(business_id, day): el segundo cierre del mismo día se rechaza en servicio.
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd7e0f4b3c5a6'
down_revision = 'c6d9f3a2b4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'verduras_cierres',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('total_sales', sa.Numeric(precision=12, scale=2),
                  nullable=False),
        sa.Column('cash_expected', sa.Numeric(precision=12, scale=2),
                  nullable=False),
        sa.Column('counted_cash', sa.Numeric(precision=12, scale=2),
                  nullable=False),
        sa.Column('difference', sa.Numeric(precision=12, scale=2),
                  nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'day',
                            name='uq_verduras_cierres_business_day'),
    )
    op.create_index('ix_verduras_cierres_business', 'verduras_cierres',
                    ['business_id'])


def downgrade() -> None:
    op.drop_index('ix_verduras_cierres_business',
                  table_name='verduras_cierres')
    op.drop_table('verduras_cierres')

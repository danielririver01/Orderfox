"""add verduras_ajustes table (correcciones de stock firmadas)

Revision ID: b5c8e2f4a1d3
Revises: a4b7e9f1c2d5
Create Date: 2026-09-23

El stock se deriva (compras − ventas − merma ± ajustes). Sin esta tabla no
hay forma honesta de corregir un conteo físico: la alternativa sería
mentir con compras falsas. Cada ajuste guarda anterior + contado +
diferencia con signo + motivo + fecha: auditable, jamás re-escribe historia.
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b5c8e2f4a1d3'
down_revision = 'a4b7e9f1c2d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'verduras_ajustes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('stock_before', sa.Numeric(precision=12, scale=3),
                  nullable=False),
        sa.Column('counted', sa.Numeric(precision=12, scale=3),
                  nullable=False),
        sa.Column('delta', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('motivo', sa.String(length=20), nullable=False,
                  server_default='conteo'),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('registered_at', sa.DateTime(timezone=True),
                  nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.ForeignKeyConstraint(['product_id'], ['verduras_products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_verduras_ajustes_business_product',
                    'verduras_ajustes', ['business_id', 'product_id'])
    op.create_index('ix_verduras_ajustes_registered',
                    'verduras_ajustes', ['business_id', 'registered_at'])


def downgrade() -> None:
    op.drop_index('ix_verduras_ajustes_registered',
                  table_name='verduras_ajustes')
    op.drop_index('ix_verduras_ajustes_business_product',
                  table_name='verduras_ajustes')
    op.drop_table('verduras_ajustes')

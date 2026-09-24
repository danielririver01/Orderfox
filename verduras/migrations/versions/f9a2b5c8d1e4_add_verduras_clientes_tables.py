"""add verduras_clientes + verduras_abonos + sale.client_id (fiados)

Revision ID: f9a2b5c8d1e4
Revises: e8f1a4b6c7d9
Create Date: 2026-09-24

Deuda como CUENTA por cliente con abonos (saldo derivado, auditable).
client_id nullable en ventas: otros métodos y ventas viejas quedan NULL
con su nombre libre intacto (sin backfill que invente dueños).
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f9a2b5c8d1e4'
down_revision = 'e8f1a4b6c7d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'verduras_clientes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('fecha_compromiso', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'name',
                            name='uq_verduras_clientes_business_name'),
    )
    op.create_index('ix_verduras_clientes_business', 'verduras_clientes',
                    ['business_id'])
    op.create_table(
        'verduras_abonos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2),
                  nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('registered_at', sa.DateTime(timezone=True),
                  nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.ForeignKeyConstraint(['client_id'], ['verduras_clientes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_verduras_abonos_client', 'verduras_abonos',
                    ['client_id'])
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('client_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_verduras_sales_client_id', 'verduras_clientes',
            ['client_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('verduras_sales', schema=None) as batch_op:
        batch_op.drop_constraint('fk_verduras_sales_client_id',
                                 type_='foreignkey')
        batch_op.drop_column('client_id')
    op.drop_index('ix_verduras_abonos_client',
                  table_name='verduras_abonos')
    op.drop_table('verduras_abonos')
    op.drop_index('ix_verduras_clientes_business',
                  table_name='verduras_clientes')
    op.drop_table('verduras_clientes')

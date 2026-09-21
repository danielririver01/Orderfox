"""add businesses table (puente multi-vertical, backfill alineado por ID)

Revision ID: a1f6e3d2b4c5
Revises: c0a5f7e8d9b1
Create Date: 2026-09-20 12:30:00.000000

Puente expand-contract (rama feature/verduras):
- Tabla `businesses` = raíz del tenant multi-vertical.
- Backfill: un Business por cada Restaurant existente, con EL MISMO ID,
  de modo que las FKs restaurant_id existentes siguen válidas sin migrar.
- Los espejos usan el ID de `restaurants` (< 1.000.000). Los verticales
  creados directamente (Business.create_direct) usan la banda >= 1.000.000
  (verduras, delivery, etc.).
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1f6e3d2b4c5'
down_revision = 'c0a5f7e8d9b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'businesses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vertical', sa.String(length=30), server_default='restaurant',
                  nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index(op.f('ix_businesses_vertical'), 'businesses', ['vertical'],
                    unique=False)

    # Backfill 1:1 alineado por ID: las FKs restaurant_id existentes siguen
    # válidas porque businesses.id == restaurants.id para cada espejo.
    op.execute(sa.text("""
        INSERT INTO businesses (id, vertical, name, slug, is_active, created_at, updated_at)
        SELECT r.id, 'restaurant', r.name, r.slug, r.is_active,
               COALESCE(r.created_at, CURRENT_TIMESTAMP),
               COALESCE(r.created_at, CURRENT_TIMESTAMP)
        FROM restaurants r
    """))


def downgrade():
    op.drop_index(op.f('ix_businesses_vertical'), table_name='businesses')
    op.drop_table('businesses')

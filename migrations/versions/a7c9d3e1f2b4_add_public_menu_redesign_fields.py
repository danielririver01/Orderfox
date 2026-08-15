"""add public menu redesign fields (cover, brand, badges)

Revision ID: a7c9d3e1f2b4
Revises: e6f0a1b2c3d4
Create Date: 2026-08-13 00:00:00.000000

Rediseño del menú digital público (variante A):
1) `restaurants`: cover_image, estimated_time, brand_color, cuisine_type
   (cuisine_type NOT NULL con server_default 'general' para backfill de filas
   existentes; sin server_default la migración falla sobre datos en producción).
2) `products`: is_vegetarian, is_spicy, is_featured (NOT NULL, server_default
   false -> backfill de filas existentes a False).

Idempotente: se verifica existencia de columna antes de operar (patrón repo).
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7c9d3e1f2b4'
down_revision = 'e6f0a1b2c3d4'
branch_labels = None
depends_on = None


def _add_column_if_missing(table, column):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns(table)}
    if column.name not in cols:
        op.add_column(table, column)


def upgrade():
    # restaurants
    _add_column_if_missing('restaurants', sa.Column('cover_image', sa.String(length=255), nullable=True))
    _add_column_if_missing('restaurants', sa.Column('estimated_time', sa.Integer(), nullable=True))
    _add_column_if_missing('restaurants', sa.Column('brand_color', sa.String(length=7), nullable=True))
    _add_column_if_missing(
        'restaurants',
        sa.Column('cuisine_type', sa.String(length=30), nullable=False,
                  server_default='general'),
    )

    # products
    _add_column_if_missing('products', sa.Column('is_vegetarian', sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing('products', sa.Column('is_spicy', sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing('products', sa.Column('is_featured', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    products_cols = {c['name'] for c in inspector.get_columns('products')}
    for col in ('is_featured', 'is_spicy', 'is_vegetarian'):
        if col in products_cols:
            op.drop_column('products', col)

    restaurants_cols = {c['name'] for c in inspector.get_columns('restaurants')}
    for col in ('cuisine_type', 'brand_color', 'estimated_time', 'cover_image'):
        if col in restaurants_cols:
            op.drop_column('restaurants', col)
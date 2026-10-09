"""add is_sold_out to products

Permite marcar "hoy no hay" sin sacar el producto del menú: el cliente lo
ve tachado con la etiqueta "Agotado" y entiende por qué no puede pedirlo.
Antes la única opción era desactivarlo, y entonces simplemente
desaparecía, sin explicación.

Revision ID: acd21a8dc37a
Revises: c9e0f1a2b3d4
Create Date: 2026-10-09

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'acd21a8dc37a'
down_revision = 'c9e0f1a2b3d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_sold_out', sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('is_sold_out')

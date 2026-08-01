"""add ntfy_topic to Restaurant

Revision ID: 697da4a0778f
Revises: a5a35021f437
Create Date: 2026-06-24 18:28:48.973057

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '697da4a0778f'
down_revision = 'a5a35021f437'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ntfy_topic', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(None, ['ntfy_topic'])


def downgrade():
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='unique')
        batch_op.drop_column('ntfy_topic')

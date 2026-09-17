"""add web search fields to restaurants

Revision ID: b7c8d9e0f1a2
Revises: a2b3c4d5e6f7
Create Date: 2026-09-15

v1.5: agrega web_search_enabled, web_search_queries_this_month y
web_search_month_reset a la tabla restaurants para la feature de
búsqueda web en tiempo real (Tavily) del Copilot VZ.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('restaurants') as batch_op:
        batch_op.add_column(
            sa.Column('web_search_enabled', sa.Boolean(),
                      server_default='0', nullable=False))
        batch_op.add_column(
            sa.Column('web_search_queries_this_month', sa.Integer(),
                      server_default='0', nullable=False))
        batch_op.add_column(
            sa.Column('web_search_month_reset', sa.DateTime(timezone=True),
                      nullable=True))


def downgrade():
    with op.batch_alter_table('restaurants') as batch_op:
        batch_op.drop_column('web_search_month_reset')
        batch_op.drop_column('web_search_queries_this_month')
        batch_op.drop_column('web_search_enabled')

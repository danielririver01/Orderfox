"""add source column to copilot_conversations

Revision ID: c6d7e8f9a0b1
Revises: b5c0d1e2f3a4
Create Date: 2026-08-04 10:00:00.000000

Fase 2 del Centro de Caja: columna `source` en copilot_conversations para
separar las conversaciones de Copilot de caja (`source='cash_register'`) de
las de /insights (`source='insights'`, default). Evita el leak de contexto
entre dos superficies con semánticas de datos distintas (paid_at vs created_at)
y permite filtrar rápido con un índice.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a0b1'
down_revision = 'b5c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('copilot_conversations')}

    if 'source' not in cols:
        op.add_column(
            'copilot_conversations',
            sa.Column('source', sa.String(30), nullable=False,
                      server_default='insights'),
        )

    indexes = {ix['name'] for ix in inspector.get_indexes('copilot_conversations')}
    if 'ix_copilot_conv_source' not in indexes:
        op.create_index('ix_copilot_conv_source', 'copilot_conversations', ['source'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {ix['name'] for ix in inspector.get_indexes('copilot_conversations')}
    if 'ix_copilot_conv_source' in indexes:
        op.drop_index('ix_copilot_conv_source', table_name='copilot_conversations')

    cols = {c['name'] for c in inspector.get_columns('copilot_conversations')}
    if 'source' in cols:
        op.drop_column('copilot_conversations', 'source')

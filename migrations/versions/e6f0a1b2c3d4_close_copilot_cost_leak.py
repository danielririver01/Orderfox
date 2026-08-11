"""close copilot cost leak: follow_up cap + ai_llm_calls telemetry

Revision ID: e6f0a1b2c3d4
Revises: c6d7e8f9a0b1
Create Date: 2026-08-06 12:00:00.000000

Cierre del agujero de costos de Copilot VZ:
1) `follow_up_count` en copilot_conversations: contador de seguimientos gratis
   por bloque de análisis. El tope lo define COPILOT_MAX_FOLLOW_UPS.
2) Tabla `ai_llm_calls`: telemetría de costo por llamada al LLM (source,
   conversation, restaurant, modelo, tokens estimados, duración).

Idempotente: se verifica existencia de columna/tabla antes de operar.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e6f0a1b2c3d4'
down_revision = 'c6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cols = {c['name'] for c in inspector.get_columns('copilot_conversations')}
    if 'follow_up_count' not in cols:
        op.add_column(
            'copilot_conversations',
            sa.Column('follow_up_count', sa.Integer(), nullable=False,
                      server_default='0'),
        )

    if not bind.dialect.has_table(bind, 'ai_llm_calls'):
        op.create_table(
            'ai_llm_calls',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source', sa.String(length=30), nullable=False),
            sa.Column('conversation_id', sa.Integer(), nullable=True),
            sa.Column('restaurant_id', sa.Integer(), nullable=False),
            sa.Column('model', sa.String(length=50), nullable=False),
            sa.Column('input_tokens_est', sa.Integer(), nullable=False),
            sa.Column('output_tokens_est', sa.Integer(), nullable=False),
            sa.Column('execution_ms', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['conversation_id'], ['copilot_conversations.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ai_llm_calls_source', 'ai_llm_calls', ['source'])
        op.create_index('ix_ai_llm_calls_conversation_id', 'ai_llm_calls', ['conversation_id'])
        op.create_index('ix_ai_llm_calls_restaurant_id', 'ai_llm_calls', ['restaurant_id'])
        op.create_index('ix_ai_llm_calls_created_at', 'ai_llm_calls', ['created_at'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if bind.dialect.has_table(bind, 'ai_llm_calls'):
        op.drop_table('ai_llm_calls')

    cols = {c['name'] for c in inspector.get_columns('copilot_conversations')}
    if 'follow_up_count' in cols:
        op.drop_column('copilot_conversations', 'follow_up_count')

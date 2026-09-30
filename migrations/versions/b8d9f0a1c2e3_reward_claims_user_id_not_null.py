"""reward_claims.user_id: align DB with model (NOT NULL)

Revision ID: b8d9f0a1c2e3
Revises: c0a5f7e8d9b1
Create Date: 2026-09-30 00:00:00.000000

VLZ-3 / R-03: la tabla se creó (d7e8f9a0b1c2) con user_id NULLABLE, pero el
modelo (`app/models/rewards.py`) lo declara NOT NULL y ambas rutas de creación
(`reward_service.generate_claim`, bonus de streak en `api_webhooks`) siempre
asignan user_id. El FK es ondelete=CASCADE, así que un usuario borrado elimina
sus claims y user_id nunca puede quedar NULL. Alineamos la base con el modelo.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b8d9f0a1c2e3'
down_revision = 'c0a5f7e8d9b1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text('SELECT COUNT(*) FROM reward_claims WHERE user_id IS NULL')
    ).scalar()
    if null_count:
        raise RuntimeError(
            f'reward_claims tiene {null_count} fila(s) con user_id NULL; '
            'resuélvelas antes de aplicar NOT NULL.'
        )
    with op.batch_alter_table('reward_claims', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(),
                              nullable=False)


def downgrade():
    with op.batch_alter_table('reward_claims', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(),
                              nullable=True)

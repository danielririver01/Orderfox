"""businesses: owner + subscription at tenant level (self-service multi-vertical)

Revision ID: b2e4c6a8d0f2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-21

Expand (backward-compatible, todo nullable/con default):
- owner_user_id → users.id (SET NULL): dueño del tenant en verticales
  directos; los espejos de restaurantes quedan NULL (su dueño sigue siendo
  User.restaurant_id, igual que siempre).
- plan_type / subscription_expires_at / has_used_trial: suscripción a nivel
  tenant — los verticales sin fila en `restaurants` necesitan su propio
  ciclo trial → activo → grace → dormant. Sin backfill: los Business
  existentes (espejos de restaurantes) quedan con el default 'trial' y
  NULL/False, que no afecta nada porque SU suscripción se sigue leyendo de
  `restaurants` vía get_subscription_status.
- pos_setup_token: token de UN SOLO USO para el setup del POS del módulo
  verduras (viaja por la DB compartida, canal del monorepo).

batch_alter_table (patrón f3b8d2c4e6a1): recrea la tabla en sqlite y usa
ALTER nativo en MySQL/MariaDB — la migración queda probada en ambos.
"""
import sqlalchemy as sa
from alembic import op

revision = 'b2e4c6a8d0f2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('businesses') as batch:
        batch.add_column(
            sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column('plan_type', sa.String(length=20), nullable=False,
                      server_default='trial'))
        batch.add_column(
            sa.Column('subscription_expires_at',
                      sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column('has_used_trial', sa.Boolean(), nullable=False,
                      server_default=sa.text('0')))
        batch.add_column(
            sa.Column('pos_setup_token', sa.String(length=64), nullable=True))
        batch.create_index('ix_businesses_owner_user_id',
                           ['owner_user_id'], unique=False)
        batch.create_foreign_key(
            'fk_businesses_owner_user_id',
            'users', ['owner_user_id'], ['id'], ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('businesses') as batch:
        batch.drop_index('ix_businesses_owner_user_id')
        batch.drop_column('pos_setup_token')
        batch.drop_column('has_used_trial')
        batch.drop_column('subscription_expires_at')
        batch.drop_column('plan_type')
        batch.drop_column('owner_user_id')

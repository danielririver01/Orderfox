"""add copilot settings to restaurants

Revision ID: a2b3c4d5e6f7
Revises: f9e2a1b3c4d5
Create Date: 2026-09-14

v1.5: agrega copilot_analysis_depth y copilot_notifications
a la tabla restaurants para la pantalla de Ajustes del Copilot VZ.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a2b3c4d5e6f7'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('restaurants') as batch_op:
        batch_op.add_column(
            sa.Column('copilot_analysis_depth', sa.String(10),
                      server_default='normal', nullable=False))
        batch_op.add_column(
            sa.Column('copilot_notifications', sa.Boolean(),
                      server_default='1', nullable=False))


def downgrade():
    with op.batch_alter_table('restaurants') as batch_op:
        batch_op.drop_column('copilot_notifications')
        batch_op.drop_column('copilot_analysis_depth')

"""add lifecycle fields to businesses (subscription_state + dormant_at)

Revision ID: d4e6f8a0b2c3
Revises: c3d5e7f9a1b2
Create Date: 2026-09-21

El modelo `Business` (app/models/business.py) y el scheduler de lifecycle
(app/tasks.py::_lifecycle_businesses) usan `subscription_state` y
`dormant_at`, pero la migración b2e4c6a8d0f2 no los creó → el registro
self-service fallaba con UndefinedColumn al insertar.

- `subscription_state` NOT NULL con server_default='active' (string, la
  convención del repo para defaults en Postgres): los espejos y filas
  existentes quedan 'active', igual que el default del modelo.
- `dormant_at` nullable (auditoría del scheduler, sin backfill).
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd4e6f8a0b2c3'
down_revision = 'c3d5e7f9a1b2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('businesses')}

    if 'subscription_state' not in cols:
        op.add_column(
            'businesses',
            sa.Column('subscription_state', sa.String(length=20),
                      nullable=False, server_default='active'),
        )
    if 'dormant_at' not in cols:
        op.add_column(
            'businesses',
            sa.Column('dormant_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('businesses')}

    if 'dormant_at' in cols:
        op.drop_column('businesses', 'dormant_at')
    if 'subscription_state' in cols:
        op.drop_column('businesses', 'subscription_state')

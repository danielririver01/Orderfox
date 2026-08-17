"""add roles to users (role, pin_hash, is_active)

Revision ID: f9e2a1b3c4d5
Revises: a7c9d3e1f2b4
Create Date: 2026-08-15 10:00:00.000000

Sistema de roles para empleados (v2.1.0):
- `role`: owner | cashier | waiter. server_default='owner' → todos los
  usuarios existentes quedan como dueño sin tocar sus filas.
- `pin_hash`: hash del PIN de 4 dígitos, solo para empleados. NULL = dueño.
- `is_active`: desactiva empleados sin borrarlos. server_default='1'.

Se escribe de forma idempotente (como f3e7d1a2b9c0) para no fallar si las
columnas ya existen en algún entorno donde se aplicaron manualmente.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f9e2a1b3c4d5'
down_revision = 'a7c9d3e1f2b4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('users')}

    if 'role' not in columns:
        op.add_column('users', sa.Column('role', sa.String(length=20), nullable=False,
                                         server_default='owner'))
    if 'pin_hash' not in columns:
        op.add_column('users', sa.Column('pin_hash', sa.String(length=255), nullable=True))
    if 'is_active' not in columns:
        op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False,
                                         server_default='1'))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('users')}

    for col in ('is_active', 'pin_hash', 'role'):
        if col in columns:
            op.drop_column('users', col)

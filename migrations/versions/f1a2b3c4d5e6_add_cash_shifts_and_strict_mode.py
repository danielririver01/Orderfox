"""add cash_shifts + strict cash mode (require_cash_shift + arqueo)

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-09-21

Turno de caja opcional configurado por el admin:
- `restaurants.require_cash_shift` (default False = flujo actual intacto).
- Tabla `cash_shifts` (apertura con fondo, cierre con conteo/diferencia).
- Columnas de arqueo en `cash_registers` (opening/expected/counted/difference/shift_id).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {t for t in inspector.get_table_names()}

    # 1. Flag en restaurants (default apagado, backward-compatible).
    cols = {c['name'] for c in inspector.get_columns('restaurants')}
    if 'require_cash_shift' not in cols:
        op.add_column(
            'restaurants',
            sa.Column('require_cash_shift', sa.Boolean(), nullable=False,
                      server_default='0'),
        )

    # 2. Tabla de turnos.
    if 'cash_shifts' not in tables:
        op.create_table(
            'cash_shifts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('restaurant_id', sa.Integer(),
                      sa.ForeignKey('restaurants.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('status', sa.String(10), nullable=False, server_default='open'),
            sa.Column('opening_amount', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('opened_by', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'),
                      nullable=True),
            sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('closed_by', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'),
                      nullable=True),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expected_cash', sa.Integer(), nullable=True),
            sa.Column('counted_cash', sa.Integer(), nullable=True),
            sa.Column('difference', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_cash_shifts_restaurant_status',
                        'cash_shifts', ['restaurant_id', 'status'])

    # 3. Columnas de arqueo en cash_registers.
    reg_cols = {c['name'] for c in inspector.get_columns('cash_registers')}
    if 'opening_amount' not in reg_cols:
        op.add_column('cash_registers',
                      sa.Column('opening_amount', sa.Integer(),
                                nullable=False, server_default='0'))
    if 'expected_cash' not in reg_cols:
        op.add_column('cash_registers',
                      sa.Column('expected_cash', sa.Integer(), nullable=True))
    if 'counted_cash' not in reg_cols:
        op.add_column('cash_registers',
                      sa.Column('counted_cash', sa.Integer(), nullable=True))
    if 'difference' not in reg_cols:
        op.add_column('cash_registers',
                      sa.Column('difference', sa.Integer(), nullable=True))
    if 'shift_id' not in reg_cols:
        op.add_column('cash_registers',
                      sa.Column('shift_id', sa.Integer(),
                                sa.ForeignKey('cash_shifts.id', ondelete='SET NULL'),
                                nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {t for t in inspector.get_table_names()}

    if 'cash_registers' in tables:
        reg_cols = {c['name'] for c in inspector.get_columns('cash_registers')}
        if 'shift_id' in reg_cols:
            op.drop_column('cash_registers', 'shift_id')
        for col in ('difference', 'counted_cash', 'expected_cash', 'opening_amount'):
            cols_now = {c['name'] for c in inspector.get_columns('cash_registers')}
            if col in cols_now:
                op.drop_column('cash_registers', col)

    if 'cash_shifts' in tables:
        idx_names = {ix['name'] for ix in inspector.get_indexes('cash_shifts')}
        if 'ix_cash_shifts_restaurant_status' in idx_names:
            op.drop_index('ix_cash_shifts_restaurant_status', table_name='cash_shifts')
        op.drop_table('cash_shifts')

    if 'restaurants' in tables:
        cols = {c['name'] for c in inspector.get_columns('restaurants')}
        if 'require_cash_shift' in cols:
            op.drop_column('restaurants', 'require_cash_shift')
